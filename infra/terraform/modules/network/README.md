# `network` module

VPC across 2 to 3 AZs: public subnets (ALB, NAT) and private subnets (ECS tasks, RDS, ElastiCache), single or per-AZ NAT, an S3 gateway endpoint so report export traffic never crosses NAT, and optional KMS / Secrets Manager interface endpoints. The default security group is locked to deny-all. VPC flow logs go to CloudWatch Logs.

Not applied in `local-floci`: the emulator has no data plane for a VPC, and locally every container shares the Compose network instead.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name, e.g. "gpuwatch-prod". | `string` | required |
| `cidr_block` | VPC CIDR. Split into /20 public subnets (low half) and /20 private subnets (high half). | `string` | `"10.41.0.0/16"` |
| `az_count` | Number of availability zones to span (2 or 3). | `number` | `3` |
| `single_nat_gateway` | One shared NAT gateway (cheaper, dev) instead of one per AZ (resilient, prod). | `bool` | `true` |
| `logs_kms_key_arn` | CMK that encrypts the flow-log group. Null uses CloudWatch's default encryption. | `string` | `null` |
| `flow_log_retention_days` | Retention for VPC flow logs (REJECT + ACCEPT) in CloudWatch Logs. 0 disables flow logs. | `number` | `30` |
| `enable_interface_endpoints` | Create KMS and Secrets Manager interface endpoints so those calls never leave the VPC. | `bool` | `true` |

## Outputs

| Name | Description |
|---|---|
| `vpc_id` | VPC id. |
| `vpc_cidr_block` | VPC CIDR. |
| `public_subnet_ids` | Public subnets (ALB, NAT). |
| `private_subnet_ids` | Private subnets (ECS tasks, RDS, ElastiCache), one per AZ. |
