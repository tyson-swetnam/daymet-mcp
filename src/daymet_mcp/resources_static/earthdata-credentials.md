# Earthdata credentials (operator only)

Points and small areas need **no login**. Areas larger than the single-pixel limit need
gridded Daymet files from NASA Earthdata, which require an Earthdata Login (EDL) token.

1. Create an account at https://urs.earthdata.nasa.gov/ and generate a user token
   (Profile > Generate Token).
2. Install the optional extra: `uv pip install 'daymet-mcp[grid]'`.
3. Start the server with the token in the environment:
   `DAYMET_MCP_EARTHDATA__TOKEN=... daymet-mcp` (or `uv run --env-file .env daymet-mcp`).

Rules:

* The token is read **only** from `DAYMET_MCP_EARTHDATA__TOKEN`: never from YAML, command
  flags, tool arguments or HTTP headers. daymet-mcp never reads `~/.netrc` or cookie files.
* It is sent as `Authorization: Bearer` only to Earthdata hosts and dropped on redirects to
  any other host. It is never logged or echoed; `--print-config` shows `***`.
* Over HTTP the Earthdata backend is off unless the operator sets
  `earthdata.allow_in_http_mode=true`, which lets every caller use the operator's quota.

Status: the Earthdata backend is **experimental**. No request with credentials has been
tested yet; that Hyrax OPeNDAP accepts bearer tokens is inferred from Earthdata
documentation.
