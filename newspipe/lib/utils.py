import logging
import re
import types
import urllib
from hashlib import md5
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests
from flask import request
from flask import url_for

from newspipe.bootstrap import application

logger = logging.getLogger(__name__)


def default_handler(obj, role="admin"):
    """JSON handler for default query formatting"""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "dump"):
        return obj.dump(role=role)
    if isinstance(obj, (set, frozenset, types.GeneratorType)):
        return list(obj)
    if isinstance(obj, BaseException):
        return str(obj)
    raise TypeError(
        "Object of type %s with value of %r "
        "is not JSON serializable" % (type(obj), obj)
    )


def try_keys(dico, *keys):
    for key in keys:
        if key in dico:
            return dico[key]
    return


def rebuild_url(url, base_split):
    split = urllib.parse.urlsplit(url)
    if split.scheme and split.netloc:
        return url  # url is fine
    new_split = urllib.parse.SplitResult(
        scheme=split.scheme or base_split.scheme,
        netloc=split.netloc or base_split.netloc,
        path=split.path,
        query="",
        fragment="",
    )
    return urllib.parse.urlunsplit(new_split)


def try_get_icon_url(url, *splits):
    for split in splits:
        if split is None:
            continue
        rb_url = rebuild_url(url, split)
        response = None
        # if html in content-type, we assume it's a fancy 404 page
        try:
            response = newspipe_get(rb_url)
            content_type = response.headers.get("content-type", "")
        except Exception:
            pass
        else:
            if (
                response is not None
                and response.ok
                and "html" not in content_type
                and response.content
            ):
                return response.url
    return None


def to_hash(text):
    return md5(text.encode("utf8") if hasattr(text, "encode") else text).hexdigest()


def clear_string(data):
    """
    Clear a string by removing HTML tags, HTML special characters
    and consecutive white spaces (more that one).
    """
    p = re.compile("<[^>]+>")  # HTML tags
    q = re.compile(r"\s")  # consecutive white spaces
    return p.sub("", q.sub(" ", data))


def safe_redirect_url(default="home"):
    next_url = request.args.get("next") or request.referrer or url_for(default)
    if next_url and urlparse(next_url).netloc != "":
        return next_url
    return None


def newspipe_get(url, **kwargs):
    request_kwargs = {
        "verify": False,
        "allow_redirects": True,
        "timeout": application.config["CRAWLER_TIMEOUT"],
        "headers": {"User-Agent": application.config["CRAWLER_USER_AGENT"]},
    }
    request_kwargs.update(kwargs)
    return requests.get(url, **request_kwargs)


def remove_case_insensitive_duplicates(input_list):
    """Remove duplicates in a list, ignoring case.
    This approach preserves the last occurrence of each unique item based on
    lowercase equivalence. The dictionary keys are all lowercase to ensure
    case-insensitive comparison, while the original case is preserved in the output.
    """
    return list({item.lower(): item for item in input_list}.values())


def push_sighting_to_vulnerability_lookup(article_uri, vulnerability_ids):
    """Create a sighting from an incoming article and push it to the Vulnerability Lookup instance."""
    print("Pushing sighting to Vulnerability Lookup...")
    headers_json = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "X-API-KEY": f"{application.config['VULNERABILITY_AUTH_TOKEN']}",
    }
    for vuln in vulnerability_ids:
        sighting = {"type": "seen", "source": article_uri, "vulnerability": vuln}
        try:
            r = requests.post(
                urljoin(
                    application.config["VULNERABILITY_LOOKUP_BASE_URL"], "sighting/"
                ),
                json=sighting,
                headers=headers_json,
            )
            if r.status_code not in (200, 201):
                print(
                    f"Error when sending POST request to the Vulnerability Lookup server: {r.reason}"
                )
        except requests.exceptions.ConnectionError as e:
            print(
                f"Error when sending POST request to the Vulnerability Lookup server:\n{e}"
            )
