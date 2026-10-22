let runtimeApiKey = ''

export function setRuntimeApiKey(value: string) {
  runtimeApiKey = value
}

export function getRuntimeApiKey() {
  return runtimeApiKey
}

export function clearRuntimeCredentials() {
  runtimeApiKey = ''
}
