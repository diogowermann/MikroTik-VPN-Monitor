# MikroTik VPN Monitor - PPP profile lifecycle hook example
#
# WARNING: importing this file REPLACES on-up and on-down for the example
# profile. Back up existing hooks and merge any unrelated logic before use.
#
# For another monitored profile/source, copy this template and change both the
# PPP profile name and sourceName. The shared sender and router credential do
# not need to change.

:local targetProfile [/ppp profile find where name="example-ovpn-profile"];
:if ([:len $targetProfile] != 1) do={
    :error "expected exactly one PPP profile named example-ovpn-profile";
}

/ppp profile set ($targetProfile->0) on-up={
    :local senderIds [/system script find where name="vpn-monitor-event-sender"];
    :if ([:len $senderIds] != 1) do={
        :log error "vpn-monitor event sender not installed";
        :return;
    }

    :local sendEvent [:parse [/system script get ($senderIds->0) source]];
    $sendEvent \
        eventType="CONNECT" \
        sourceName="primary-ovpn" \
        serviceName="ovpn" \
        vpnUser=$user \
        vpnCallerId=$"caller-id" \
        vpnLocalAddress=$"local-address" \
        vpnRemoteAddress=$"remote-address" \
        vpnInterfaceId=$interface;
}

/ppp profile set ($targetProfile->0) on-down={
    :local senderIds [/system script find where name="vpn-monitor-event-sender"];
    :if ([:len $senderIds] != 1) do={
        :log error "vpn-monitor event sender not installed";
        :return;
    }

    :local sendEvent [:parse [/system script get ($senderIds->0) source]];
    $sendEvent \
        eventType="DISCONNECT" \
        sourceName="primary-ovpn" \
        serviceName="ovpn" \
        vpnUser=$user \
        vpnCallerId=$"caller-id" \
        vpnLocalAddress=$"local-address" \
        vpnRemoteAddress=$"remote-address" \
        vpnInterfaceId=$interface;
}
