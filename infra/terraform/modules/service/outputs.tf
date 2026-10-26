output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "url" {
  description = "Public URL of the deployment."
  value       = "https://${var.hostname}"
}

output "alb_dns_name" {
  description = "Load balancer DNS name (CNAME target when the zone is not in Route53)."
  value       = aws_lb.this.dns_name
}

output "alb_arn_suffix" {
  description = "Load balancer ARN suffix, for CloudWatch metrics."
  value       = aws_lb.this.arn_suffix
}

output "services" {
  description = "Load-balanced services: { api = { service_name, target_group_arn_suffix }, web = { ... } }."
  value = {
    for k in keys(local.load_balanced) : k => {
      service_name            = aws_ecs_service.this[k].name
      target_group_arn_suffix = aws_lb_target_group.this[k].arn_suffix
    }
  }
}

output "service_names" {
  description = "Every ECS service name (api, worker, web)."
  value       = { for k, s in aws_ecs_service.this : k => s.name }
}

output "security_group_ids" {
  description = "Task security group per app."
  value       = { for k, sg in aws_security_group.task : k => sg.id }
}

output "task_role_arns" {
  description = "Task role per app."
  value       = { for k, r in aws_iam_role.task : k => r.arn }
}

output "run_task" {
  description = "Parameters for one-off tasks: `gpuwatch migrate` (default), `seed-demo` or `create-owner` as a command override."
  value = {
    cluster         = aws_ecs_cluster.this.name
    task_definition = aws_ecs_task_definition.this["migrate"].family
    container       = "migrate"
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.task["migrate"].id]
  }
}
