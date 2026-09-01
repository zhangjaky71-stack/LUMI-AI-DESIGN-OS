variable "project" { type = string }
variable "environment" { type = string }
variable "runtime_names" {
  type = set(string)
  default = [
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
  ]

  validation {
    condition = (
      length(var.runtime_names) == 6 &&
      alltrue([
        for name in var.runtime_names :
        can(regex("^[a-z0-9][a-z0-9-]{1,62}$", name))
      ])
    )
    error_message = "runtime_names must contain exactly six lowercase runtime repository names."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
