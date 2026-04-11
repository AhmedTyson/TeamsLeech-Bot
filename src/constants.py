"""
Shared constants for the TeamsLeech Bot.

Centralises magic strings and URLs used across multiple modules
so they are defined in exactly one place.

Public API
----------
GRAPH_BASE_URL : str
    Microsoft Graph API v1.0 base URL.
"""

# Microsoft Graph API v1.0 endpoint — used by fetcher and uploader
GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
