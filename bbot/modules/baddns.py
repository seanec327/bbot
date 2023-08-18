from baddns.lib import baddns as BadDNS
from .base import BaseModule


class baddns(BaseModule):
    watched_events = ["DNS_NAME", "DNS_NAME_UNRESOLVED"]
    produced_events = ["FINDING", "VULNERABILITY"]
    flags = ["active", "safe", "web-basic"]
    meta = {"description": "Check subdomains for for subdomain takeovers and other DNS tomfoolery"}
    max_event_handlers = 2
    deps_pip = ["baddns"]

    async def handle_event(self, event):
        baddns_cname = BadDNS.BadDNS_cname(
            event.data, http_client_class=self.scan.helpers.web.AsyncClient, dns_client=self.scan.helpers.dns.resolver
        )
        if await baddns_cname.dispatch():
            results = baddns_cname.analyze()
            if results and len(results) > 0:
                for r in results:
                    data = {
                        "severity": "MEDIUM",
                        "description": f"Probable Subdomain Takeover. CNAME: [{r['cnames']}] Signature Name: [{r.get('signature_name', 'N/A')}] Matching Domain: [{r.get('matching_domain', 'N/A')}] Technique: [{r['technique']}]",
                        "host": str(event.host),
                    }
                    self.emit_event(data, "VULNERABILITY", event)
