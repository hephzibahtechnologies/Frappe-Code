# SBIQC Production Routing (Option A — wildcard DNS + wildcard TLS)

One-time infra setup for multi-tenant provisioning. None of this can be done
from inside this repo/CI — it requires access to the DNS provider and the
production server itself.

## 1. Wildcard DNS

Add an A record with your DNS provider:

```
*.sbiqc.com   A   <production server's public IP>
```

This makes every current and future tenant subdomain resolve automatically —
no per-tenant DNS work needed when a new tenant is provisioned.

## 2. Wildcard TLS certificate

A wildcard cert requires the **DNS-01** ACME challenge (HTTP-01 cannot
validate wildcards). The exact certbot command depends on your DNS provider's
API — tell me which one you use (Cloudflare, Route53, GoDaddy, etc.) and I'll
give you the exact plugin + command. Generic shape:

```
sudo certbot certonly --dns-<provider> \
  -d sbiqc.com -d '*.sbiqc.com'
```

Certbot auto-renews wildcard certs the same as normal ones as long as the
DNS plugin credentials stay configured.

## 3. Nginx

Install `infra/nginx/sbiqc-wildcard.conf` (see comments in that file for the
exact commands). This is a **single, static config** — it never needs
regenerating or reloading when a new tenant is provisioned, since it already
matches every subdomain and Frappe's own `dns_multitenant` routing (already
enabled in `sites/common_site_config.json`) does the per-tenant dispatch once
the request reaches the bench container.

## 4. Verify

Once all three are in place, `_setup_production_routing()` in
`apps/sbiqc_provisioning/sbiqc_provisioning/provisioner/engine.py` performs an
automatic health check (`GET https://<site_name>/api/method/ping`) at the end
of every tenant provisioning run — if DNS/Nginx/cert aren't wired up
correctly, provisioning will fail loudly with the tenant marked `Error`
instead of silently succeeding with an unreachable site.
