# Service Levels And Alerts

## Indicators And Objectives

| User path | Indicator | Objective | Window |
| --- | --- | --- | --- |
| Open control plane | Prometheus `up` for engine plus `/health/ready=200` | 99.5% | 30 days |
| Complete accepted runs | `SUCCEEDED / (SUCCEEDED + FAILED)` | 99% excluding user cancellations | 7 days |
| Deliver accepted payloads | `succeeded / (succeeded + dead_letter)` | 99% | 7 days |
| Recover capacity DB | Verified restore and integrity within RTO | 100% of quarterly drills under 30 minutes | Quarterly |

These are self-hosted single-node objectives, not a contractual multi-region SLA. Planned maintenance is recorded separately but still visible in readiness history.

## Alerts

Prometheus rules are in `documentation/alerts.yml`.

- `SiftlaneDown`: follow deployment and incident runbooks; check container and database.
- `SiftlaneQueueBacklog`: pause schedules and inspect workers/resources.
- `SiftlaneRunFailureRatio`: inspect run events and disable the smallest failing flow/connector.
- `SiftlaneDeliveryDeadLetters`: pause the target, correct credentials/receiver and replay selectively.
- `SiftlaneDatabaseGrowth`: verify disk and retention, then re-run capacity qualification.

Every alert annotation links to the repository runbook path so an operator can proceed without the implementation author.
