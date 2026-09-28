"""External data clients and parsers."""

from tickerlens.data.proxy_env import sanitize_proxy_env

# The sandbox runtime injects bracketed IPv6 literals (e.g. "[::1]") into
# no_proxy/NO_PROXY. httpx < 0.28.x's get_environment_proxies() does not
# recognize the bracketed form, builds an "all://*[...]" mount key, and
# URLPattern raises InvalidURL — which crashes EVERY httpx.Client()
# construction in the process (EDGAR, Wikipedia, ...). Strip the brackets
# once at import so all downstream httpx usage works. Same host, valid form.
sanitize_proxy_env()
