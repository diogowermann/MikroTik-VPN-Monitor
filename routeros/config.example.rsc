# MikroTik VPN Monitor - RouterOS configuration example
#
# Copy this file to a private working location before editing it.
# Replace every placeholder locally. Never commit the edited production copy.
# Importing this template replaces only the named vpn-monitor-config script.

:local existingConfig [/system script find where name="vpn-monitor-config"];
:if ([:len $existingConfig] > 0) do={
    /system script remove $existingConfig;
}

/system script add name="vpn-monitor-config" policy=read source={
    :return ({
        "apiBase"="https://vpn-api.example.com/api/v1";
        "routerId"="00000000-0000-0000-0000-000000000000";
        "routerSecret"="REPLACE_WITH_ROUTER_SECRET";
    });
}
