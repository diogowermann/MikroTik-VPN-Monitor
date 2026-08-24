# MikroTik VPN Monitor - shared lifecycle event sender
#
# This script is not intended to be executed directly. PPP on-up/on-down hooks
# parse its source and call it as a function with source-specific arguments.

:local existingSender [/system script find where name="vpn-monitor-event-sender"];
:if ([:len $existingSender] > 0) do={
    /system script remove $existingSender;
}

/system script add name="vpn-monitor-event-sender" policy=read,test source={
    :local configIds [/system script find where name="vpn-monitor-config"];
    :if ([:len $configIds] != 1) do={
        :error "vpn-monitor-config must exist exactly once";
    }

    :local getConfig [:parse [/system script get ($configIds->0) source]];
    :local monitorConfig [$getConfig];
    :local apiBase [:tostr ($monitorConfig->"apiBase")];
    :local routerId [:tostr ($monitorConfig->"routerId")];
    :local routerSecret [:tostr ($monitorConfig->"routerSecret")];

    :if ([:len $apiBase] = 0 || [:len $routerId] = 0 || [:len $routerSecret] = 0) do={
        :error "vpn-monitor-config is incomplete";
    }

    :local eventDate [/system clock get date];
    :local eventTime [/system clock get time];
    :local eventOffset [/system clock get gmt-offset];
    :local occurredAt ($eventDate . "T" . $eventTime . $eventOffset);
    :local eventId ("ev-" . [:rndstr length=32]);

    :local payload ({
        "contract_version"=1;
        "event_id"=$eventId;
        "event_type"=[:tostr $eventType];
        "source_id"=[:tostr $sourceName];
        "service"=[:tostr $serviceName];
        "username"=[:tostr $vpnUser];
        "caller_id"=[:tostr $vpnCallerId];
        "local_address"=[:tostr $vpnLocalAddress];
        "remote_address"=[:tostr $vpnRemoteAddress];
        "interface_id"=[:tostr $vpnInterfaceId];
        "occurred_at"=$occurredAt;
    });

    :local requestBody [:serialize value=$payload to=json options=json.no-string-conversion];
    :local requestUrl ($apiBase . "/router/events");
    :local requestHeaders ("Content-Type:application/json,X-Router-ID:" . $routerId . ",Authorization:Bearer " . $routerSecret);

    :local deliveryFailed [:onerror deliveryError {
        :retry command={
            /tool fetch url=$requestUrl http-method=post http-header-field=$requestHeaders http-data=$requestBody check-certificate=yes output=none;
        } delay=1 max=3;
    } do={
        :log error ("vpn-monitor event delivery failed source=" . [:tostr $sourceName] . " user=" . [:tostr $vpnUser] . " error=" . $deliveryError);
    }];

    :if ($deliveryFailed) do={
        :return false;
    }

    :log info ("vpn-monitor event delivered type=" . [:tostr $eventType] . " source=" . [:tostr $sourceName] . " user=" . [:tostr $vpnUser]);
    :return true;
}
