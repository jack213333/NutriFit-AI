import axios from 'axios'

export const api = axios.create({
  baseURL: '',
  timeout: 60000
})

export async function getSummary() {
  return (await api.get('/api/dashboard/summary')).data
}

export async function calcProfile(payload: any) {
  return (await api.post('/api/profile/calculate', payload)).data
}

export async function chat(question: string, topK = 6) {
  return (await api.post('/api/rag/chat', { question, top_k: topK })).data
}

export async function agentChat(payload: any) {
  return (await api.post('/api/agent/chat', payload)).data
}

export async function getChatHistory(sessionId: string) {
  return (await api.get(`/api/chat/history/${sessionId}`)).data
}

export async function retrieve(question: string, topK = 6) {
  return (await api.post('/api/rag/retrieve', { question, top_k: topK })).data
}

export async function logFood(items: any[], note = '') {
  return (await api.post('/api/food/log', { items, note })).data
}

export async function getFoodRecords() {
  return (await api.get('/api/food/records')).data
}

export async function recognizeFood(file: File, mealType = '拍照记录') {
  const form = new FormData()
  form.append('file', file)
  form.append('meal_type', mealType)
  return (await api.post('/api/food/recognize', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })).data
}

export async function knowledgeStats() {
  return (await api.get('/api/knowledge/stats')).data
}

export async function saveBodyMetric(payload: any) {
  return (await api.post('/api/memory/body-metrics', payload)).data
}

export async function getBodyMetrics() {
  return (await api.get('/api/memory/body-metrics')).data
}

export async function getPublicConfig() {
  return (await api.get('/api/config/public')).data
}

export async function clearFoodRecords() {
  return (await api.post('/api/admin/clear-food-records')).data
}

export async function clearAllData() {
  return (await api.post('/api/admin/clear-all-data')).data
}

export interface StreamHandlers {
  onStage?: (step: any) => void
  onDelta?: (content: string) => void
  onDone?: (payload: any) => void
  onError?: (message: string) => void
}

async function consumeSSE(response: Response, handlers: StreamHandlers) {
  if (!response.ok || !response.body) {
    handlers.onError?.(`请求失败（HTTP ${response.status}）`)
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data: ')) continue
        let event: any
        try {
          event = JSON.parse(line.slice(6))
        } catch {
          continue
        }
        if (event.type === 'stage') handlers.onStage?.(event.step)
        else if (event.type === 'delta') handlers.onDelta?.(event.content)
        else if (event.type === 'done') handlers.onDone?.(event)
        else if (event.type === 'error') handlers.onError?.(event.message)
      }
    }
  }
}

export async function agentChatStream(payload: any, handlers: StreamHandlers, signal?: AbortSignal) {
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal
  })
  await consumeSSE(response, handlers)
}

export async function ragChatStream(question: string, topK = 6, handlers: StreamHandlers, signal?: AbortSignal) {
  const response = await fetch('/api/rag/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
    signal
  })
  await consumeSSE(response, handlers)
}

export async function updateFeatures(key: string, value: boolean) {
  return (await api.post('/api/config/features', { key, value })).data
}
