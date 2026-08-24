# MikroTik VPN Monitor - shared /ppp active snapshot sender
#
# This script is parsed and called by one source-specific scheduled wrapper.
# profileNames is optional. When present, local /ppp secret profile membership
# is used to decide which active sessions belong to this source.

:local existingSender [/system script find where name="vpn-monitor-snapshot-sender"];
:if ([:len $existingSender] > 0) do={
    /system script remove $existingSender;
}

/system script add name="vpn-monitor-snapshot-sender" policy=read,test source={
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

    :local allowedProfiles [:toarray ""];
    :if ([:typeof $profileNames] != "nil") do={
        :set allowedProfiles $profileNames;
    }

    :local snapshotDate [/system clock get date];
    :local snapshotTime [/system clock get time];
    :local snapshotOffset [/system clock get gmt-offset];
    :local observedAt ($snapshotDate . "T" . $snapshotTime . $snapshotOffset);

    :local observedSessions [:toarray ""];
    :local skippedByProfile 0;
    :local activeRows [/ppp active print as-value where service=$serviceName];

    :foreach activeRow in=$activeRows do={
        :local includeSession true;
        :local vpnName [:tostr ($activeRow->"name")];

        :if ([:len $allowedProfiles] > 0) do={
            :set includeSession false;
            :local secretIds [/ppp secret find where name=$vpnName];
            :if ([:len $secretIds] = 1) do={
                :local activeProfile [:tostr [/ppp secret get ($secretIds->0) profile]];
                :foreach allowedProfile in=$allowedProfiles do={
                    :if ($activeProfile = [:tostr $allowedProfile]) do={
                        :set includeSession true;
                    }
                }
            }
        }

        :if ($includeSession) do={
            :local routerSessionId [:tostr ($activeRow->"session-id")];
            :if ([:len $routerSessionId] > 0) do={
                :local uptimeSeconds 0;
                :if ([:typeof ($activeRow->"uptime")] != "nil") do={
                    :set uptimeSeconds ([:tonsec value=($activeRow->"uptime")] / 1000000000);
                }

                :local sessionPayload ({
                    "router_session_id"=$routerSessionId;
                    "username"=$vpnName;
                    "service"=[:tostr ($activeRow->"service")];
                    "caller_id"=[:tostr ($activeRow->"caller-id")];
                    "address"=[:tostr ($activeRow->"address")];
                    "uptime_seconds"=$uptimeSeconds;
                });
                :set observedSessions ($observedSessions, $sessionPayload);
            }
        } else={
            :set skippedByProfile ($skippedByProfile + 1);
        }
    }

    :if ($skippedByProfile > 0) do={
        :log warning ("vpn-monitor snapshot skipped " . $skippedByProfile . " active session(s) because local PPP profile membership could not be matched");
    }

    :local payload ({
        "contract_version"=1;
        "source_id"=[:tostr $sourceName];
        "observed_at"=$observedAt;
        "sessions"=$observedSessions;
    });

    :local requestBody [:serialize value=$payload to=json options=json.no-string-conversion];
    :local requestUrl ($apiBase . "/router/snapshot");
    :local requestHeaders ("Content-Type:application/json,X-Router-ID:" . $routerId . ",Authorization:Bearer " . $routerSecret);

    :local deliveryFailed [:onerror deliveryError {
        :retry command={
            /tool fetch url=$requestUrl http-method=post http-header-field=$requestHeaders http-data=$requestBody check-certificate=yes output=none;
        } delay=1 max=3;
    } do={
        :log error ("vpn-monitor snapshot delivery failed source=" . [:tostr $sourceName] . " error=" . $deliveryError);
    }];

    :if ($deliveryFailed) do={
        :return false;
    }

    :log debug ("vpn-monitor snapshot delivered source=" . [:tostr $sourceName] . " sessions=" . [:len $observedSessions]);
    :return true;
}
