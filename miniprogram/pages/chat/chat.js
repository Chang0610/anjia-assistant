// Set this to a configured HTTPS request domain before phone testing or release.
const API_BASE = 'http://127.0.0.1:8765'

Page({
  data: { draft: '', loading: false, displayMessages: [], lastId: '' },
  onInput(event) { this.setData({ draft: event.detail.value }) },
  send() {
    const content = this.data.draft.trim()
    if (!content || this.data.loading) return
    const item = { id: `m${Date.now()}`, role: 'user', content }
    const displayMessages = this.data.displayMessages.concat(item)
    this.setData({ draft: '', loading: true, displayMessages, lastId: item.id })
    const messages = displayMessages.filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }))
    wx.request({
      url: `${API_BASE}/api/chat`,
      method: 'POST',
      data: { messages },
      timeout: 40000,
      success: res => {
        const ok = res.statusCode === 200
        const answer = ok ? res.data.answer : `暂时无法生成回答：${res.data.error || '服务异常'}`
        this.appendAnswer(answer, ok ? 'assistant' : 'error')
      },
      fail: () => this.appendAnswer('连接失败。请确认后端已启动，并检查小程序请求域名设置。', 'error'),
    })
  },
  appendAnswer(content, role) {
    const item = { id: `m${Date.now()}a`, role, content }
    this.setData({ loading: false, displayMessages: this.data.displayMessages.concat(item), lastId: item.id })
  },
})
