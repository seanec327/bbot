from bbot.modules.base import InterceptModule


class cloud(InterceptModule):
    watched_events = ["*"]
    meta = {"description": "Tag events by cloud provider, identify cloud resources like storage buckets"}
    scope_distance_modifier = 1
    _priority = 3

    async def setup(self):
        self.dummy_modules = {}
        for provider_name in self.helpers.cloud.providers:
            self.dummy_modules[provider_name] = self.scan._make_dummy_module(f"cloud_{provider_name}", _type="scan")
        return True

    async def filter_event(self, event):
        if (not event.host) or (event.type in ("IP_RANGE",)):
            return False, "event does not have host attribute"
        return True

    async def handle_event(self, event, kwargs):
        # cloud tagging by hosts
        hosts_to_check = set(str(s) for s in event.resolved_hosts)
        hosts_to_check.add(str(event.host_original))
        for host in hosts_to_check:
            provider, provider_type, subnet = self.helpers.cloudcheck(host)
            if provider:
                event.add_tag(f"{provider_type}-{provider}")

        found = set()
        # look for cloud assets in hosts, http responses
        # loop through each provider
        for provider in self.helpers.cloud.providers.values():
            provider_name = provider.name.lower()
            base_kwargs = dict(
                source=event, tags=[f"{provider.provider_type}-{provider_name}"], _provider=provider_name
            )
            # loop through the provider's regex signatures, if any
            for event_type, sigs in provider.signatures.items():
                if event_type != "STORAGE_BUCKET":
                    raise ValueError(f'Unknown cloudcheck event type "{event_type}"')
                base_kwargs["event_type"] = event_type
                for sig in sigs:
                    matches = []
                    if event.type == "HTTP_RESPONSE":
                        matches = await self.helpers.re.findall(sig, event.data.get("body", ""))
                    elif event.type.startswith("DNS_NAME"):
                        for host in hosts_to_check:
                            match = sig.match(host)
                            if match:
                                matches.append(match.groups())
                    for match in matches:
                        if not match in found:
                            found.add(match)

                            _kwargs = dict(base_kwargs)
                            event_type_tag = f"cloud-{event_type}"
                            _kwargs["tags"].append(event_type_tag)
                            if event.type.startswith("DNS_NAME"):
                                event.add_tag(event_type_tag)

                            if event_type == "STORAGE_BUCKET":
                                bucket_name, bucket_domain = match
                                _kwargs["data"] = {
                                    "name": bucket_name,
                                    "url": f"https://{bucket_name}.{bucket_domain}",
                                }
                                await self.emit_event(**_kwargs)

    async def emit_event(self, *args, **kwargs):
        provider_name = kwargs.pop("_provider")
        dummy_module = self.dummy_modules[provider_name]
        event = dummy_module.make_event(*args, **kwargs)
        if event:
            await super().emit_event(event)