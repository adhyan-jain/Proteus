# Feature Coverage Report: Live OpenFlow 1.3 to Deployment Model Schema

This audit report details the mapping between live OpenFlow 1.3 `OFPFlowStatsReply` telemetry counters and the active model input schema (`models/releases/v001/feature_schema.json`, 52 features).

| # | Feature Name | Telemetry Source | Live Populated | Default Value | Mapping / Reason |
|---|---|---|---|---|---|
| 1 | `duration` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 2 | `src_bytes` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 3 | `dst_bytes` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 4 | `land` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 5 | `wrong_fragment` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 6 | `urgent` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 7 | `hot` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 8 | `num_failed_logins` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 9 | `logged_in` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 10 | `num_compromised` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 11 | `root_shell` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 12 | `su_attempted` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 13 | `num_root` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 14 | `num_file_creations` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 15 | `num_shells` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 16 | `num_access_files` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 17 | `num_outbound_cmds` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 18 | `is_host_login` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 19 | `is_guest_login` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 20 | `count` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 21 | `srv_count` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 22 | `serror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 23 | `srv_serror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 24 | `rerror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 25 | `srv_rerror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 26 | `same_srv_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 27 | `diff_srv_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 28 | `srv_diff_host_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 29 | `dst_host_count` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 30 | `dst_host_srv_count` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 31 | `dst_host_same_srv_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 32 | `dst_host_diff_srv_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 33 | `dst_host_same_src_port_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 34 | `dst_host_srv_diff_host_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 35 | `dst_host_serror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 36 | `dst_host_srv_serror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 37 | `dst_host_rerror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 38 | `dst_host_srv_rerror_rate` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 39 | `protocol_type_icmp` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 40 | `protocol_type_tcp` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 41 | `protocol_type_udp` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 42 | `service_domain_u` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 43 | `service_ftp` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 44 | `service_http` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 45 | `service_other` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 46 | `service_private` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 47 | `service_smtp` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 48 | `service_telnet` | OpenFlow match/counter translation rule | `TRUE` | `N/A` | N/A (Populated) |
| 49 | `flag_REJ` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 50 | `flag_RSTO` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 51 | `flag_S0` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |
| 52 | `flag_SF` | None | `FALSE` | `0.0` | Not exposed by aggregate OpenFlow 1.3 counters (requires DPI / packet-in payload parsing) |

## Summary Statistics
- **Total Model Features**: 52
- **Directly / Indirectly Populated**: 13
- **Safely Defaulted (Unpopulated)**: 39

## Methodology & Architectural Policy
1. **Strict Non-Fabrication**: Features that require Deep Packet Inspection (DPI) or TCP flag tracking that are unavailable in aggregate OpenFlow 1.3 counters are never fabricated with hallucinated random numbers. They default deterministically to 0.0.
2. **Deterministic Projection**: `sdn.topology.feature_mapper.map_schema_to_feature_vector()` ensures that vector indices strictly align with `feature_schema.json` order.
