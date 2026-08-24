# MikroTik VPN Monitor - source-specific snapshot example
#
# Copy this template for each enabled source that should reconcile current
# state. profileNames can contain one or more local PPP profile names.

:local existingScript [/system script find where name="vpn-monitor-snapshot-primary"];
:if ([:len $existingScript] > 0) do={
    /system script remove $existingScript;
}

/system script add name="vpn-monitor-snapshot-primary" policy=read,test source={
    :local senderIds [/system script find where name="vpn-monitor-snapshot-sender"];
    :if ([:len $senderIds] != 1) do={
        :log error "vpn-monitor snapshot sender not installed";
        :return;
    }

    :local sendSnapshot [:parse [/system script get ($senderIds->0) source]];
    $sendSnapshot \
        sourceName="primary-ovpn" \
        serviceName="ovpn" \
        profileNames={"example-ovpn-profile"};
}

:local existingScheduler [/system scheduler find where name="vpn-monitor-snapshot-primary"];
:if ([:len $existingScheduler] > 0) do={
    /system scheduler remove $existingScheduler;
}

/system scheduler add \
    name="vpn-monitor-snapshot-primary" \
    start-time=startup \
    interval=1m \
    on-event="/system script run vpn-monitor-snapshot-primary" \
    policy=read,test;
