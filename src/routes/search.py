import html
import urllib.parse

import sanic
import sanic_ext

import npf_renderer
from .. import privblur_extractor

search = sanic.Blueprint("search", url_prefix="/search")


@search.get("/")
async def query_param_redirect(request: sanic.Request): 
    """Endpoint for /search to redirect q= queries to /search/<query>"""
    if query := request.args.get("q"):
        return sanic.redirect(request.app.url_for("search._main", query=urllib.parse.quote(query, safe="~")))
    else:
        return sanic.redirect(request.app.url_for("explore._trending"))


@search.get("/<query:str>")
async def _main(request: sanic.Request, query: str):
    query = urllib.parse.unquote(query)
    timeline_type = request.app.ctx.TumblrAPI.config.TimelineType

    time_filter = request.args.get("t")
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    initial_results = await _query_search(request, query, days=time_filter)

    timeline = privblur_extractor.parse_container(initial_results)

    return await _render(request, timeline, query, f"/search/{html.escape(query)}", time_filter=time_filter, sort_by="popular", post_filter=None)


@search.get("/<query:str>/recent")
async def _sort_by_search(request: sanic.Request, query: str):
    query = urllib.parse.unquote(query)
    time_filter = request.args.get("t")

    # Ignore time filter when its invalid
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    initial_results = await _query_search(request, query, days=time_filter, latest=True)
    timeline = privblur_extractor.parse_container(initial_results)

    endpoint = f"/search/{html.escape(query)}/recent"

    return await _render(request, timeline, query, endpoint, time_filter=time_filter, sort_by="recent", post_filter=None)


@search.get("/<query:str>/<post_filter:str>")
async def _filter_by_search(request: sanic.Request, query: str, post_filter: str):
    return await _request_search_filter_post(request, query, post_filter, latest=False)

@search.get("/<query:str>/recent/<post_filter:str>")
async def _sort_by_and_filter_search(request: sanic.Request, query: str, post_filter: str):
    return await _request_search_filter_post(request, query, post_filter, latest=True)

async def _request_search_filter_post(request, query, post_filter, latest):
    query = urllib.parse.unquote(query)
    post_filter = urllib.parse.unquote(post_filter)

    time_filter = request.args.get("t")
    post_filter = getattr(request.app.ctx.TumblrAPI.config.PostTypeFilters, post_filter.upper(), None)

    # As to match Tumblr's behavior we redirect to the main /search endpoint when the
    # given post filter is invalid
    #
    # If we are sorting by the latest posts then we redirect to /search/recent 
    if not post_filter:
        if latest:
           url = request.app.url_for("search._sort_by_search", query=urllib.parse.quote(query))
        else:
            url = request.app.url_for("search._main", query=urllib.parse.quote(query))

        url += f"?{request.query_string}" if request.query_string else ""
        return sanic.redirect(url)

    # Ignore time filter when its invalid
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    initial_results = await _query_search(request, query, days=time_filter, post_type_filter=post_filter, latest=latest)

    post_filter = post_filter.name.lower()

    timeline = privblur_extractor.parse_container(initial_results)

    if latest:
        endpoint = f"/search/{html.escape(query)}/recent/{post_filter}"
        sort_by = "recent"
    else:
        sort_by = "popular"
        endpoint = f"/search/{html.escape(query)}/{post_filter}"

    return await _render(request, timeline, query, endpoint, post_filter=post_filter, time_filter=time_filter, sort_by=sort_by)


async def _query_search(request, query, **kwargs):
    "Queries the search endpoint"
    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    return await request.app.ctx.TumblrAPI.timeline_search(query, request.app.ctx.TumblrAPI.config.TimelineType.POST, continuation=continuation, **kwargs)


async def _render(request, timeline, query, endpoint, **kwargs):

    context = {
        "app": request.app, "timeline": timeline, "query_args": request.args, "query": query, "endpoint": endpoint,
        "url_escape": urllib.parse.quote, "url_handler": request.app.ctx.URL_HANDLER, 
        "format_npf": npf_renderer.format_npf, "html_escape": html.escape,
    }

    context.update(kwargs)

    return await sanic_ext.render("search.jinja", context=context)