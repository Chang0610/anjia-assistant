const STORAGE_KEY = 'shanghai-relocation-calendar-v1'
const USER_KEY = 'shanghai-relocation-user-v1'
const PROFILE_GROUPS = [
  { title: '基本情况', fields: [['name', '称呼', '例如：小林'], ['destination_city', '搬去的城市'], ['current_city', '目前所在城市'], ['company_city', '公司所在城市'], ['company_district', '公司所在区域'], ['company_location', '公司详细位置', '例如：张江高科附近'], ['employment_type', '就业情况']] },
  { title: '时间与预算', fields: [['start_date', '入职时间'], ['move_deadline', '计划完成搬家时间'], ['housing_handover_date', '新住处交房日'], ['planning_start_date', '开始规划日'], ['full_process_deadline', '全流程目标完成日'], ['availability_constraints', '可用时间约束'], ['moving_budget', '一次性搬家预算', '例如：3000元'], ['monthly_rent_budget', '每月租房预算', '例如：3500元/月'], ['commute_preference', '通勤偏好']] },
  { title: '住房与办事', fields: [['shared_housing', '是否接受合租'], ['pets', '宠物情况'], ['housing_preferences', '住房偏好'], ['current_housing', '当前住房情况', '例如：旧租约10月20日到期'], ['social_insurance', '社保情况', '例如：原单位9月缴至月底'], ['medical_insurance', '医保情况', '例如：担心换工作断缴'], ['housing_fund', '公积金情况', '例如：需从外地转入'], ['household_registration', '居住证或落户需求', '例如：需要办理居住证'], ['other_requirements', '其他已确认需求', '例如：远程办公，需要稳定宽带']] },
]
const PROFILE_FIELDS = PROFILE_GROUPS.flatMap(group => group.fields.map(field => field[0]))
const DISTRICTS = ['黄浦区','徐汇区','长宁区','静安区','普陀区','虹口区','杨浦区','浦东新区','闵行区','宝山区','嘉定区','金山区','松江区','青浦区','奉贤区','崇明区']
const COMMUTE = ['10分钟内','20分钟内','30分钟内','30-60分钟','60-90分钟','两小时以内','随便']
const REMINDER_TIMES = Array.from({ length: 31 }, (_, index) => `${String(7 + Math.floor(index / 2)).padStart(2, '0')}:${index % 2 ? '30' : '00'}`)
const HOUSING_OPTIONS = ['离地铁口近','附近有商场','附近有菜市场','附近有医院']
let cityOptions = []
let pickerState = null
const userState = loadUserState()
const messages = userState.conversation
const today = shanghaiTodayParts()
let viewMonth = new Date(today.year, today.month - 1, 1)
let selectedDate = shanghaiTodayKey()
let calendarState = loadCalendar()
saveCalendar()
let proposalSelection = new Set()
let busy = false
let directPlanRequest = false
let onboardingStep = 0
const onboardingDraft = { ...userState.profile }

const chat = document.querySelector('#chat')
const input = document.querySelector('#chat-input')
const send = document.querySelector('#send')
const proposalWrap = document.querySelector('#proposal-wrap')
let lastRequestError = null
function attachFeedback(row, message) {
  if (!row || !message || !message.content) return
  const controls = el('div', 'answer-feedback')
  controls.appendChild(el('span', '', '这条回答有帮助吗？'))
  for (const [value, label] of [['helpful', '有帮助'], ['inaccurate', '信息不准'], ['missing', '缺少依据']]) {
    const button = el('button', `feedback-choice${message.feedback === value ? ' selected' : ''}`, label)
    button.type = 'button'
    button.setAttribute('aria-pressed', message.feedback === value ? 'true' : 'false')
    button.addEventListener('click', async () => {
      message.feedback = value
      controls.querySelectorAll('button').forEach(item => {
        item.classList.toggle('selected', item === button)
        item.setAttribute('aria-pressed', item === button ? 'true' : 'false')
      })
      saveUserState()
      try {
        const response = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rating: value, response_mode: message.responseMode || 'unknown' }) })
        if (!response.ok) throw new Error('反馈未同步')
      } catch (_) {
        controls.querySelector('.feedback-status')?.remove()
        controls.appendChild(el('span', 'feedback-status', '反馈已保存在本机，稍后可重新选择提交。'))
      }
    })
    controls.appendChild(button)
  }
  row.querySelector('.bubble')?.appendChild(controls)
}
// The date picker is shared by profile fields and proposal dates. Keep it at
// phone level so it can open while the chat view is active too.
const sharedProfilePicker = document.querySelector('#profile-picker')
if (sharedProfilePicker) document.querySelector('.phone').appendChild(sharedProfilePicker)

function loadUserState() {
  try {
    const value = JSON.parse(localStorage.getItem(USER_KEY) || '{}')
    const profile = value.profile && typeof value.profile === 'object' ? value.profile : {}
    const conversation = Array.isArray(value.conversation) ? value.conversation.filter(item => item && ['user', 'assistant'].includes(item.role) && typeof item.content === 'string') : []
    const inputs = Array.isArray(value.inputs) ? value.inputs.filter(item => item && typeof item.content === 'string') : []
    const reminders = value.reminders && typeof value.reminders === 'object' ? value.reminders : {}
    return { profile, conversation, inputs, reminders: { inApp: reminders.inApp !== false, wechat: reminders.wechat === true, threeDays: /^\d{2}:\d{2}$/.test(reminders.threeDays || '') ? reminders.threeDays : '09:00', dueDay: /^\d{2}:\d{2}$/.test(reminders.dueDay || '') ? reminders.dueDay : '08:30' }, updatedAt: value.updatedAt || null, onboardingDone: value.onboardingDone === true }
  } catch (_) {
    return { profile: {}, conversation: [], inputs: [], reminders: { inApp: true, wechat: false, threeDays: '09:00', dueDay: '08:30' }, updatedAt: null, onboardingDone: false }
  }
}

function saveUserState() {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify({ ...userState, conversation: messages.slice(-40) }))
    return true
  } catch (_) {
    document.querySelector('#profile-status').textContent = '本机存储空间不足，本次信息未保存。'
    document.querySelector('.footnote').textContent = '本机存储空间不足，本次资料未保存。请到“我的”检查。'
    return false
  }
}

function updateIntro() {
  const profile = userState.profile
  const known = [profile.destination_city, profile.company_location, profile.start_date, profile.commute_preference, profile.monthly_rent_budget].filter(Boolean)
  if (known.length) {
    document.querySelector('#intro-bubble').textContent = `我已记住你的情况：${known.join('、')}。可以直接问下一步；信息有变化时告诉我，或到“我的”修改。`
  } else {
    document.querySelector('#intro-bubble').textContent = '可以先说：入职时间、公司位置、搬家完成时间和一次性搬家预算。通勤、合租与月租预算之后都可以补充。'
  }
}

function needsOnboarding() {
  const core = ['company_location', 'start_date', 'move_deadline', 'moving_budget', 'commute_preference', 'shared_housing']
  return !userState.onboardingDone && messages.length === 0 && core.filter(key => userState.profile[key]).length < 3
}

function onboardingInput(form, label, key, type, placeholder, required = true) {
  const field = el('label', 'onboarding-field')
  field.appendChild(el('span', '', label))
  const control = el('input')
  control.name = key
  control.type = type
  control.required = required
  control.placeholder = placeholder || ''
  if (type === 'date') {
    const todayKey = shanghaiTodayKey()
    control.min = todayKey
    const savedDate = parseDateValue(onboardingDraft[key])
    control.value = savedDate && savedDate >= todayKey ? savedDate : ''
  } else control.value = (onboardingDraft[key] || '').replace(/元(?:\/月)?$/, '')
  field.appendChild(control)
  form.appendChild(field)
}

function onboardingSelect(form, label, key, options) {
  const field = el('label', 'onboarding-field')
  field.appendChild(el('span', '', label))
  const control = el('select')
  control.className = 'onboarding-native-select'
  control.name = key
  control.required = true
  control.appendChild(new Option('请选择', ''))
  for (const option of options) control.appendChild(new Option(option, option))
  control.value = key === 'shared_housing' ? selectValue(key, onboardingDraft[key] || '') : onboardingDraft[key] || ''
  const dropdown = el('div', 'cute-dropdown onboarding-dropdown')
  const trigger = el('button', 'cute-trigger', control.value || '请选择')
  trigger.type = 'button'; trigger.setAttribute('aria-label', label); trigger.setAttribute('aria-expanded', 'false'); trigger.classList.toggle('has-value', Boolean(control.value))
  const optionsBox = el('div', 'cute-options'); optionsBox.hidden = true
  for (const choice of options) {
    const option = el('button', 'cute-option', choice); option.type = 'button'; option.classList.toggle('selected', control.value === choice)
    option.addEventListener('click', () => { control.value = choice; trigger.textContent = choice; trigger.classList.add('has-value'); optionsBox.querySelectorAll('.cute-option').forEach(item => item.classList.toggle('selected', item === option)); optionsBox.hidden = true; trigger.setAttribute('aria-expanded', 'false') })
    optionsBox.appendChild(option)
  }
  trigger.addEventListener('click', () => { optionsBox.hidden = !optionsBox.hidden; trigger.setAttribute('aria-expanded', String(!optionsBox.hidden)) })
  dropdown.append(control, trigger, optionsBox); field.appendChild(dropdown)
  form.appendChild(field)
}

function renderOnboarding() {
  const card = document.querySelector('#onboarding-card')
  card.replaceChildren()
  const visible = needsOnboarding()
  card.hidden = !visible
  document.querySelector('#intro-row').hidden = visible
  if (!visible) return
  const titles = ['先确定目的地', '把时间和预算放进来']
  card.appendChild(el('div', 'onboarding-progress', `只需 2 步 · ${onboardingStep + 1}/2`))
  card.appendChild(el('h2', '', titles[onboardingStep]))
  card.appendChild(el('p', '', ['目前先服务上海。告诉我公司的大致位置，就能开始倒排计划。', '日期用来安排先后；搬家预算、通勤、合租和月租预算都可以稍后补充。'][onboardingStep]))
  const form = el('form', 'onboarding-form')
  if (onboardingStep === 0) {
    const destination = el('div', 'onboarding-destination', '搬去的城市  ·  上海')
    form.appendChild(destination)
    onboardingInput(form, '公司位置或办公枢纽', 'company_location', 'text', '例如：张江高科、陆家嘴')
  } else if (onboardingStep === 1) {
    onboardingInput(form, '入职时间', 'start_date', 'date')
    onboardingInput(form, '希望完成搬家的时间', 'move_deadline', 'date')
  }
  const actions = el('div', 'onboarding-actions')
  if (onboardingStep) {
    const back = el('button', 'onboarding-back', '上一步')
    back.type = 'button'
    back.addEventListener('click', () => { onboardingStep -= 1; renderOnboarding() })
    actions.appendChild(back)
  }
  const next = el('button', 'primary', onboardingStep === 1 ? '保存并生成计划' : '下一步')
  next.type = 'submit'
  actions.appendChild(next)
  form.appendChild(actions)
  form.addEventListener('submit', event => {
    event.preventDefault()
    if (!form.reportValidity()) return
    for (const control of form.elements) {
      if (!control.name) continue
      const value = control.value.trim()
      onboardingDraft[control.name] = /budget/.test(control.name) && value ? `${value}元` : value
    }
    if (onboardingStep < 1) { onboardingStep += 1; renderOnboarding(); return }
    userState.profile = { ...userState.profile, ...onboardingDraft, destination_city: '上海' }
    userState.onboardingDone = true
    userState.updatedAt = new Date().toISOString()
    saveUserState()
    updateIntro()
    renderOnboarding()
    directPlanRequest = true
    input.value = '请根据我已保存的信息直接生成一份完整的安家计划清单，覆盖入职确认、日期冲突处理、找房入住、旧住处收尾、搬家、宽带、公积金及其他必要事项。请把全部事项放入待确认计划，不要先输出普通问答。'
    document.querySelector('#chat-form').requestSubmit()
  })
  card.appendChild(form)
  const skip = el('button', 'onboarding-skip onboarding-skip-top', '跳过')
  skip.type = 'button'
  skip.addEventListener('click', () => { userState.onboardingDone = true; saveUserState(); renderOnboarding(); input.focus() })
  card.appendChild(skip)
}

function dateKey(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function shanghaiTodayKey() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const part = key => parts.find(item => item.type === key)?.value || '00'
  return `${part('year')}-${part('month')}-${part('day')}`
}

function shanghaiTodayParts() {
  const [year, month, day] = shanghaiTodayKey().split('-').map(Number)
  return { year, month, day }
}

function addCalendarDays(key, count) {
  const [year, month, day] = key.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1, day + count))
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-${String(value.getUTCDate()).padStart(2, '0')}`
}

function clampProposalDates(events, confirmed = []) {
  const todayKey = shanghaiTodayKey()
  const existingIds = new Set(confirmed.map(event => event.id))
  return (events || []).map(event => {
    const next = { ...event }
    if (existingIds.has(next.id) || next.date_basis !== '建议日期') return next
    if (next.due_date && next.due_date < todayKey) next.due_date = todayKey
    if (next.start_date && next.start_date < todayKey) next.start_date = todayKey
    if (next.start_date && next.due_date && next.start_date > next.due_date) next.start_date = next.due_date
    return next
  })
}

function dedupeCurrentEvents(events) {
  const todayKey = shanghaiTodayKey()
  const seen = new Set()
  return (events || []).filter(event => {
    // Keep past history intact, but only retain one current or future copy of an event.
    if (event.due_date && event.due_date < todayKey) return true
    const key = String(event.title || '').replace(/[\s\u3000，。、“”‘’：:；;（）()、/·-]/g, '').toLowerCase()
    if (!key || seen.has(key)) return !key
    seen.add(key)
    return true
  })
}

function loadCalendar() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    const pending = Array.isArray(value.pending) ? dedupeCurrentEvents(value.pending) : null
    return {
      confirmed: Array.isArray(value.confirmed) ? dedupeCurrentEvents(value.confirmed) : [],
      pending,
      changes: Array.isArray(value.changes) ? value.changes : [],
      bulkDeleteAll: value.bulkDeleteAll === true,
      pendingOnlyDelete: value.pendingOnlyDelete === true,
      bulkDeletePreviousPending: Array.isArray(value.bulkDeletePreviousPending) ? value.bulkDeletePreviousPending : null,
      bulkDeletePreviousChanges: Array.isArray(value.bulkDeletePreviousChanges) ? value.bulkDeletePreviousChanges : [],
    }
  } catch (_) {
    return { confirmed: [], pending: null, changes: [], bulkDeleteAll: false, pendingOnlyDelete: false, bulkDeletePreviousPending: null, bulkDeletePreviousChanges: [] }
  }
}

function saveCalendar() {
  try {
    const serialized = JSON.stringify(calendarState)
    localStorage.setItem(STORAGE_KEY, serialized)
    return localStorage.getItem(STORAGE_KEY) === serialized
  } catch (_) {
    return false
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function appendEventSources(container, event) {
  const sources = Array.isArray(event.sources) ? event.sources : []
  if (!sources.length && !event.source_note) return
  const details = el('details', 'event-sources')
  details.appendChild(el('summary', '', '依据与状态'))
  if (event.source_note) details.appendChild(el('div', 'source-basis', event.source_note))
  for (const source of sources) {
    const entry = el('div', 'source-entry')
    if (source.source_url?.startsWith('https://')) {
      const link = el('a', 'evidence-link', source.source_name || '查看来源')
      link.href = source.source_url
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      entry.appendChild(link)
    } else entry.appendChild(el('div', '', source.source_name || '信息待确认'))
    entry.appendChild(el('div', 'source-meta', [source.source_status, source.verified_at ? `核验时间：${source.verified_at}` : ''].filter(Boolean).join(' · ')))
    details.appendChild(entry)
  }
  container.appendChild(details)
}

function addMessage(role, content, evidence = [], structuredSources = []) {
  const row = el('div', `row ${role}`)
  const bubble = el('div', 'bubble')
  content = String(content || '').replace(/\\n/g, '\n')
  if (role === 'assistant' && content.includes('最后追问：')) {
    const index = content.lastIndexOf('最后追问：')
    const before = content.slice(0, index).trimEnd()
    const questions = content.slice(index + '最后追问：'.length).split('\n')
      .map(line => line.trim().replace(/^(?:\d+[.、．)]|[一二三四五六七八九十]+[、.．)])\s*/, ''))
      .filter(line => /[？?]$/.test(line) && !/^(?:请补充|补充|请核对|核对|先完成|完成后|请查看|查看|请办理|办理后|建议先)/.test(line))
      .slice(0, 3)
    content = questions.length ? `${before}\n最后追问：\n${questions.map((line, number) => `${number + 1}. ${line}`).join('\n')}` : before
  }
  content = content.replace(/(最后追问：|近期要完成的事：|接下来按以下顺序推进：|你需要做的是：|关键假设：|需要确认的假设：|需要确认：|请确认：|你可以直接发给HR：|信息状态与依据：|依据与状态：)([^\n]*)/g, (_, heading, items) => {
    const separated = items.replace(/[；;]/g, '\n').replace(/\s+(?=(?:\d+|[一二三四五六七八九十])[、.)．])/g, '\n')
    return `${heading}\n${separated.trim()}`
  })
  content = content
    .replace(/\s*(?=依据与状态：)/g, '\n')
    .replace(/\s*(?=(?:关键假设|需要确认的假设|需要确认|请确认|你可以直接发给HR|信息状态与依据|依据与状态)：)/g, '\n')
    .replace(/依据与状态：([\s\S]*?)(?=\n(?:目前信息总结|近期要完成的事|事项详情|最后追问|你可以直接发给HR|关键假设|需要确认)|$)/g, (_, body) => `依据与状态：${body.replace(/\n+/g, '；').trim()}`)
    .replace(/([：。；！？])\s*(?=[一二三四五六七八九十]+、)/g, '$1\n')
    .replace(/\s+(?=[一二三四五六七八九十]+、)/g, '\n')
  if (role === 'assistant' && (evidence.length || /(?:依据与状态|信息依据或入口)：/.test(content))) {
    const annotations = new Map(evidence.map(item => [item.line, item]))
    const structured = [...structuredSources]
    content.split('\n').forEach((line, index) => {
      const sourceLine = /^(信息依据或入口|依据与状态)：/.test(line)
      const part = sourceLine ? el('details', 'answer-line answer-source') : el('div', 'answer-line', line || '\u00a0')
      const contentPart = sourceLine ? el('div', 'answer-source-body') : part
      if (sourceLine) {
        const summary = el('summary', '', '依据与状态')
        part.append(summary, contentPart)
      }
      if (/^(目前信息总结|近期要完成的事|事项详情|最后追问|关键假设|需要确认|你可以直接发给HR|信息状态与依据|依据与状态)/.test(line)) part.classList.add('answer-heading')
      else if (/^(为何|何时|前置条件|完成标准)：/.test(line)) part.classList.add('answer-field')
      const sourceData = sourceLine ? structured.shift() : null
      if (sourceLine && sourceData) {
        contentPart.replaceChildren()
        const basis = String(sourceData.basis || '').replace(/https?:\/\/\S+/g, '').trim()
        if (basis) contentPart.appendChild(el('div', 'source-basis', basis))
        for (const source of sourceData.sources || []) {
          const entry = el('div', 'source-entry')
          if (source.source_url) {
            const link = el('a', 'evidence-link', source.source_name || '来源')
            link.href = source.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer'
            entry.appendChild(link)
          } else entry.appendChild(el('span', '', source.source_name || '信息待确认'))
          entry.appendChild(el('div', 'source-meta', [source.source_status, source.verified_at ? `核验时间：${source.verified_at}` : ''].filter(Boolean).join(' · ')))
          contentPart.appendChild(entry)
        }
        bubble.appendChild(part)
        return
      }
      const sourceUrls = [...line.matchAll(/https?:\/\/[^\s；，。）》）]+/g)].map(match => match[0])
      if (sourceLine && sourceUrls.length) {
        const raw = line.replace(/^(信息依据或入口|依据与状态)：\s*/, '').replace(/\[来源\]\(https?:\/\/[^)]+\)/g, '').replace(/https?:\/\/[^\s；，。）》）]+/g, '').replace(/，{2,}/g, '，').trim()
        const segments = raw.split(/[；;]/).map(item => item.trim()).filter(Boolean)
        const status = segments.filter(item => /官方来源已核验|核验日期|验证日期|数据日期/.test(item)).join('；')
        const entries = segments.filter(item => !/官方来源已核验|核验日期|验证日期|数据日期/.test(item))
        contentPart.replaceChildren()
        entries.forEach((item, itemIndex) => {
          const row = el('div', 'source-entry', `${itemIndex + 1}. ${item}`)
          if (sourceUrls[itemIndex]) { const link = el('a', 'evidence-link', '来源'); link.href = sourceUrls[itemIndex]; link.target = '_blank'; link.rel = 'noopener noreferrer'; row.appendChild(document.createTextNode(' ')); row.appendChild(link) }
          contentPart.appendChild(row)
        })
        if (status) contentPart.appendChild(el('div', 'answer-status', status))
        return
      }
      if (sourceUrls.length) {
        const visible = line
          .replace(/^(信息依据或入口|依据与状态)：\s*/, '')
          .replace(/\[来源\]\(https?:\/\/[^)]+\)/g, '')
          .replace(/https?:\/\/[^\s；，。）》）]+/g, '')
          .replace(/，{2,}/g, '，')
          .replace(/来源：\s*；?/g, '')
          .replace(/来源:\s*;?/g, '')
          .replace(/\s{2,}/g, ' ')
          .trim()
        contentPart.textContent = visible
        if (sourceLine) contentPart.classList.add('answer-status')
        sourceUrls.forEach(url => {
          const link = el('a', 'evidence-link', '来源')
          link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'
          contentPart.appendChild(document.createTextNode(' ')); contentPart.appendChild(link)
        })
      }
      const annotation = annotations.get(index)
      if (annotation) {
        const badges = el('div', 'evidence-badges')
        for (const tag of annotation.tags || []) badges.appendChild(el('span', `evidence-badge${/待确认|待核验/.test(tag) ? ' pending' : ''}`, tag))
        if (annotation.verified_url) {
          const link = el('a', 'evidence-link', '来源')
          link.href = annotation.verified_url
          link.target = '_blank'
          link.rel = 'noopener noreferrer'
          badges.appendChild(link)
        }
        contentPart.appendChild(badges)
      }
      bubble.appendChild(part)
    })
  } else bubble.textContent = content
  row.appendChild(bubble)
  chat.appendChild(row)
  chat.scrollTop = chat.scrollHeight
  return row
}

function setTab(name) {
  document.querySelector('#chat-view').hidden = name !== 'chat'
  document.querySelector('#calendar-view').hidden = name !== 'calendar'
  document.querySelector('#profile-view').hidden = name !== 'profile'
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === name))
  if (name === 'calendar') renderCalendar()
  if (name === 'profile') renderProfile()
  if (name === 'chat') renderInAppReminders()
}

function showProposalStart() {
  if (proposalWrap.hidden) return
  const cardTop = proposalWrap.getBoundingClientRect().top
  const chatTop = chat.getBoundingClientRect().top
  chat.scrollTop += cardTop - chatTop - 8
}

function renderInAppReminders() {
  const banner = document.querySelector('#in-app-reminders')
  if (!banner) return
  const current = shanghaiTodayKey()
  const horizon = addCalendarDays(current, 3)
  const due = userState.reminders.inApp
    ? calendarState.confirmed.filter(item => {
        if (item.done || !item.due_date) return false
        if (item.reminder_at) return item.reminder_at <= `${current}T${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date())}` && item.due_date >= current
        return item.due_date >= current && item.due_date <= horizon
      }).sort((a, b) => a.due_date.localeCompare(b.due_date)).slice(0, 3)
    : []
  banner.hidden = due.length === 0
  if (due.length) banner.textContent = `近期提醒 · ${due.map(item => `${item.title}（${item.due_date === current ? '今天' : item.due_date.slice(5)}）`).join('、')}  ›`
}
document.querySelector('#in-app-reminders')?.addEventListener('click', () => setTab('calendar'))
setInterval(renderInAppReminders, 60000)

document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => setTab(tab.dataset.tab)))
fetch('/health').then(response => response.json()).then(status => {
  const mode = document.querySelector('#mode')
  if (!mode) return
  mode.textContent = status.demo_mode
    ? '本地演示模式：固定规则回答；日历提议需连接 GPT。'
    : status.llm_configured ? 'GPT 已连接 · 日程仅在你确认后保存。' : '尚未配置大模型，请按 README 设置接口。'
}).catch(() => { const mode = document.querySelector('#mode'); if (mode) mode.textContent = '无法连接服务。' })

document.querySelector('#chat-form').addEventListener('submit', async event => {
  event.preventDefault()
  const content = input.value.trim()
  if (!content || busy) return
  lastRequestError?.remove()
  lastRequestError = null
  const wasDirectPlanRequest = directPlanRequest
  input.value = ''
  messages.push({ role: 'user', content })
  userState.inputs.push({ content, at: new Date().toISOString() })
  saveUserState()
  renderOnboarding()
  const userRow = addMessage('user', content)
  busy = true
  send.disabled = true
  const waiting = addMessage('assistant', '正在为您规划中')
  waiting.classList.add('planning-status')
  // Yield once so the loading state is painted before the model request begins.
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messages.slice(-24).map(({ role, content }) => ({ role, content })), profile: userState.profile, calendar: { confirmed: calendarState.confirmed, pending: calendarState.bulkDeleteAll ? calendarState.bulkDeletePreviousPending : calendarState.pending } }),
    })
    const data = await response.json()
    waiting.remove()
    if (!response.ok) throw new Error(data.error || '服务异常')
    const answerRow = directPlanRequest ? null : addMessage('assistant', data.answer, data.answer_evidence || [], data.answer_sources || [])
    if (!directPlanRequest && Array.isArray(data.quick_choices) && data.quick_choices.length) {
      const choices = el('div', 'quick-choice-row')
      data.quick_choices.slice(0, 4).forEach(choice => {
        const button = el('button', 'quick-choice', choice)
        button.type = 'button'
        button.addEventListener('click', () => {
          input.value = choice
          document.querySelector('#chat-form').requestSubmit()
        })
        choices.appendChild(button)
      })
      answerRow?.appendChild(choices)
    }
    if (!directPlanRequest) {
      const answerMessage = { role: 'assistant', content: data.answer, evidence: data.answer_evidence || [], sources: data.answer_sources || [], responseMode: data.response_mode || 'unknown' }
      messages.push(answerMessage)
      attachFeedback(answerRow, answerMessage)
    }
    directPlanRequest = false
    if (data.profile && typeof data.profile === 'object') {
      userState.profile = data.profile
      userState.updatedAt = new Date().toISOString()
      updateIntro()
    }
    saveUserState()
    if (Array.isArray(data.calendar_clarifications) && data.calendar_clarifications.length) {
      const questions = data.calendar_clarifications.map(item => {
        const oldDate = item.existing_date || '日期待确认'
        const newDate = item.proposed_date || '日期待确认'
        const proposed = item.proposed_title && item.proposed_title !== item.existing_title ? `，新内容为“${item.proposed_title}”` : ''
        if (item.existing_status === 'pending') {
          return `待确认草案中已有“${item.existing_title}”（${oldDate}），本次建议可能将其改为 ${newDate}${proposed}。这条事项尚未加入计划日历，是否要调整草案？`
        }
        return `计划日历中已有“${item.existing_title}”（${oldDate}），本次信息可能将其改为 ${newDate}${proposed}。是否要更改这条已确认日程？`
      })
      const clarificationText = questions.join('\n')
      addMessage('assistant', clarificationText)
      messages.push({ role: 'assistant', content: clarificationText })
      saveUserState()
    }
    if (data.proposal?.clear_pending) {
      calendarState.pending = null
      calendarState.changes = []
      calendarState.bulkDeleteAll = false
      calendarState.pendingOnlyDelete = false
      calendarState.bulkDeletePreviousPending = null
      calendarState.bulkDeletePreviousChanges = []
      proposalSelection = new Set()
      saveCalendar()
      renderProposal()
      renderInAppReminders()
      const removed = (data.proposal.removed_pending || []).map(item => `“${item.title}”`).join('、')
      addMessage('assistant', removed ? `已从待确认清单撤销${removed}，当前计划日历没有变化。` : '已撤销待确认的改动，当前计划日历没有变化。')
    } else if (data.proposal) {
      if (data.proposal.bulk_delete_all && !calendarState.bulkDeleteAll) {
        calendarState.bulkDeletePreviousPending = calendarState.pending
        calendarState.bulkDeletePreviousChanges = calendarState.changes
      } else if (!data.proposal.bulk_delete_all) {
        calendarState.bulkDeletePreviousPending = null
        calendarState.bulkDeletePreviousChanges = []
      }
      calendarState.bulkDeleteAll = data.proposal.bulk_delete_all === true
      calendarState.pendingOnlyDelete = data.proposal.pending_only_delete === true
      calendarState.pending = clampProposalDates(data.proposal.events, calendarState.confirmed)
      calendarState.changes = data.proposal.changes
      const proposalBase = calendarState.pendingOnlyDelete ? calendarState.bulkDeletePreviousPending || [] : calendarState.confirmed
      proposalSelection = new Set(scopedProposalImpact(calendarState.pending, proposalBase).changes.map(change => (change.next || change.old).id))
      saveCalendar()
      renderProposal()
      renderInAppReminders()
      if (!data.proposal.bulk_delete_all && Array.isArray(data.proposal.removed_pending) && data.proposal.removed_pending.length) {
        addMessage('assistant', `已从待确认清单撤销：${data.proposal.removed_pending.map(item => item.title).join('、')}。已确认的计划日历没有因此删除事项。`)
      }
    }
    if (wasDirectPlanRequest && (!data.proposal || !data.proposal.changes?.length) && !data.calendar_clarifications?.length) {
      addMessage('error', '计划暂时没有生成成功，当前资料已保存。请点击发送重试，或补充信息后再次生成。')
    }
    // Keep the response first and the confirmation card second in the same scroll area.
    if (data.proposal?.bulk_delete_all && !proposalWrap.hidden) showProposalStart()
    else if (answerRow) chat.scrollTop = answerRow.offsetTop - chat.offsetTop
  } catch (error) {
    waiting.remove()
    userRow.remove()
    messages.pop()
    userState.inputs.pop()
    saveUserState()
    input.value = content
    lastRequestError = addMessage('error', `暂时无法回答：${error.message}。你的问题已保留。`)
    const retry = el('button', 'retry-request', '重试发送')
    retry.type = 'button'
    retry.addEventListener('click', () => document.querySelector('#chat-form').requestSubmit())
    lastRequestError.querySelector('.bubble')?.appendChild(retry)
  } finally {
    directPlanRequest = false
    busy = false
    send.disabled = false
    input.focus()
  }
})

function eventDateLabel(event) {
  if (!event.due_date) return '日期待确认'
  const start = event.start_date || event.due_date
  return `${start !== event.due_date ? start + ' 至 ' : ''}${event.due_date}${event.due_time ? ' ' + event.due_time : ''}`
}

function proposalDateLabel(event) {
  return event.due_date ? `${event.due_date}${event.due_time ? ' ' + event.due_time : ''}` : '日期待确认'
}

function visibleOnDate(event, key) {
  return Boolean(event.due_date && (event.start_date || event.due_date) <= key && key <= event.due_date)
}

function protectedDeadline(event) {
  return event?.hard_deadline === true || (event?.kind === 'deadline' && event?.date_basis === '用户明确')
}

function proposalImpact(candidate, confirmed) {
  const before = new Map(confirmed.map(item => [item.id, item]))
  const after = new Map(candidate.map(item => [item.id, item]))
  const changes = []
  const hardIssues = []
  for (const next of candidate) {
    const old = before.get(next.id)
    if (!old) { changes.push({ old: null, next, kind: 'add' }); continue }
    const dateChanged = old.start_date !== next.start_date || old.due_date !== next.due_date || old.due_time !== next.due_time
    const changed = ['title', 'detail', 'kind', 'hard_deadline', 'date_basis', 'source_note', 'reminder_at', 'done'].some(key => old[key] !== next[key])
    if (dateChanged || changed) changes.push({ old, next, kind: dateChanged ? 'move' : 'edit' })
    if (protectedDeadline(old) && (dateChanged || !protectedDeadline(next))) hardIssues.push({ id: old.id, title: old.title, text: `${eventDateLabel(old)} → ${eventDateLabel(next)}` })
  }
  for (const old of confirmed) {
    if (after.has(old.id)) continue
    changes.push({ old, next: null, kind: 'delete' })
    if (protectedDeadline(old)) hardIssues.push({ id: old.id, title: old.title, text: `拟删除原定 ${eventDateLabel(old)} 的硬截止` })
  }
  return { changes, hardIssues }
}

function scopedProposalImpact(candidate, confirmed) {
  const all = proposalImpact(candidate, confirmed)
  const scoped = new Map((calendarState.changes || [])
    .filter(change => change && change.id)
    .map(change => [change.id, change.type]))
  if (!scoped.size) return all
  const kindFor = type => type === '新增' ? 'add' : type === '删除' ? 'delete' : 'edit'
  const changes = all.changes
    .filter(change => scoped.has((change.next || change.old).id))
    .map(change => ({ ...change, kind: kindFor(scoped.get((change.next || change.old).id)) }))
  const selectedIds = new Set(changes.map(change => (change.next || change.old).id))
  return { changes, hardIssues: all.hardIssues.filter(issue => selectedIds.has(issue.id)) }
}

function selectedImpact(candidate, confirmed) {
  const all = proposalImpact(candidate, confirmed).changes
  const selected = all.filter(change => proposalSelection.has((change.next || change.old).id))
  const effective = confirmed.filter(old => !selected.some(change => (change.next || change.old).id === old.id))
  effective.push(...selected.filter(change => change.next).map(change => change.next))
  return proposalImpact(effective, confirmed)
}

proposalSelection = calendarState.pending
  ? new Set(scopedProposalImpact(calendarState.pending, calendarState.confirmed).changes.map(change => (change.next || change.old).id))
  : new Set()

function proposalOrder(event) {
  const title = event.title || ''
  if (/HR|入职|报到|日期冲突/.test(title)) return 0
  if (/租房|看房|房源|签约|入住/.test(title)) return 1
  if (/搬家|旧住处|退租|交接/.test(title)) return 2
  if (/宽带|水电|燃气/.test(title)) return 3
  if (/公积金|社保|医保|居住登记|居住证/.test(title)) return 4
  return 5
}

function openProposalDatePicker(event) {
  const todayKey = shanghaiTodayKey()
  const selected = event.due_date && event.due_date >= todayKey ? event.due_date : todayKey
  const [year, month, day] = selected.split('-').map(Number)
  pickerState = { key: 'proposal_date', values: [year, month, day], onConfirm: value => {
    const target = calendarState.pending?.find(item => item.id === event.id)
    if (!target) return
    const safeValue = value < todayKey ? todayKey : value
    target.due_date = safeValue
    target.start_date = safeValue
    target.date_basis = '用户明确'
    renderProposal()
  } }
  document.querySelector('#picker-title').textContent = `设置“${event.title}”日期`
  document.querySelector('#picker-search-wrap').hidden = true
  document.querySelector('#picker-city-labels').hidden = true
  const columns = document.querySelector('#picker-columns')
  columns.replaceChildren()
  buildWheel(columns, Array.from({ length: 41 }, (_, i) => 2020 + i), 0, value => `${value}年`)
  buildWheel(columns, Array.from({ length: 12 }, (_, i) => i + 1), 1, value => `${value}月`)
  buildDayWheel(columns)
  document.querySelector('#profile-picker').hidden = false
  requestAnimationFrame(() => columns.querySelectorAll('.wheel-column').forEach(column => { column.scrollTop = Number(column.dataset.index) * 42 }))
}

function renderProposal() {
  proposalWrap.replaceChildren()
  if (calendarState.pending) calendarState.pending = clampProposalDates(calendarState.pending, calendarState.confirmed)
  const events = calendarState.pending
  if (!events || !calendarState.changes.length) {
    proposalWrap.hidden = true
    return
  }
  proposalWrap.hidden = false
  const card = el('div', 'proposal-card')
  card.appendChild(el('div', 'proposal-title', calendarState.bulkDeleteAll ? '待确认删除的计划清单' : '以下是我为你整理的计划清单'))
  card.appendChild(el('div', 'proposal-sub proposal-lead', calendarState.bulkDeleteAll ? '请核对要删除的事项；确认前已确认日程保持不变。' : '请勾选本次要新增、修改或删除的事项，确认后才会写入计划日历。'))
  const proposalBase = calendarState.pendingOnlyDelete ? calendarState.bulkDeletePreviousPending || [] : calendarState.confirmed
  const impact = scopedProposalImpact(events, proposalBase)
  if (!impact.changes.length) {
    proposalWrap.hidden = true
    return
  }
  const counts = [
    ['新增', impact.changes.filter(item => item.kind === 'add').length],
    ['修改', impact.changes.filter(item => item.kind === 'move' || item.kind === 'edit').length],
    ['删除', impact.changes.filter(item => item.kind === 'delete').length],
  ].filter(([, count]) => count).map(([label, count]) => `${label} ${count} 项`)
  card.appendChild(el('div', 'proposal-sub', `仅显示本次改动：${counts.join(' · ')}。确认前日历不变。`))
  if (calendarState.bulkDeleteAll && !calendarState.pendingOnlyDelete) {
    const confirmedIds = new Set(calendarState.confirmed.map(item => item.id))
    const draftCount = (calendarState.bulkDeletePreviousPending || []).filter(item => !confirmedIds.has(item.id)).length
    if (draftCount) card.appendChild(el('div', 'proposal-sub', `另有 ${draftCount} 项尚未加入日历的待确认草案，将在你确认删除时一并撤销。`))
  }
  const table = el('table', 'proposal-table proposal-plan-table')
  const head = el('thead')
  const headRow = el('tr')
  for (const label of ['待办事务', '预计期限', '']) headRow.appendChild(el('th', '', label))
  head.appendChild(headRow)
  table.appendChild(head)
  const body = el('tbody')
  const orderedChanges = [...impact.changes].sort((a, b) => {
    const left = a.next || a.old; const right = b.next || b.old
    const leftDate = left.due_date || '9999-12-31'
    const rightDate = right.due_date || '9999-12-31'
    return leftDate.localeCompare(rightDate) || proposalOrder(left) - proposalOrder(right) || left.title.localeCompare(right.title)
  })
  for (const change of orderedChanges) {
    const event = change.next || change.old
    const row = el('tr')
    const content = el('td', 'proposal-task-cell')
    content.appendChild(el('div', 'event-title', change.old && change.next && change.old.title !== change.next.title ? `${change.old.title} → ${change.next.title}` : event.title))
    if (change.kind !== 'delete' && event.detail) content.appendChild(el('div', 'event-note', event.detail))
    if (change.kind !== 'delete' && event.reminder_at && change.old?.reminder_at !== event.reminder_at) content.appendChild(el('div', 'event-note', `站内提醒：${change.old?.reminder_at?.replace('T', ' ') || '未设置'} → ${event.reminder_at.replace('T', ' ')}`))
    if (change.kind !== 'delete') appendEventSources(content, event)
    row.appendChild(content)
    const dateCell = el('td', 'proposal-date-cell')
    if (change.kind !== 'delete') {
      const dateButton = el('button', 'proposal-date-button', '')
      dateButton.type = 'button'
      if (change.old && change.next && change.old.due_date !== change.next.due_date) {
        const oldDate = el('span', 'proposal-old-date', proposalDateLabel(change.old))
        const newDate = el('span', 'proposal-new-date', proposalDateLabel(event))
        dateButton.append(oldDate, newDate)
      } else {
        dateButton.textContent = proposalDateLabel(event)
      }
      dateButton.addEventListener('click', () => openProposalDatePicker(event))
      dateCell.appendChild(dateButton)
      dateCell.appendChild(el('small', '', event.due_date ? '可滑动修改' : '点击选择日期'))
    }
    const selectCell = el('td', 'proposal-select-cell')
    if (change.kind === 'delete') selectCell.appendChild(el('span', 'proposal-delete-note', '删除'))
    const select = el('button', `proposal-select${proposalSelection.has(event.id) ? ' selected' : ''}`, proposalSelection.has(event.id) ? '✓' : '')
    select.type = 'button'; select.setAttribute('aria-label', `${proposalSelection.has(event.id) ? '取消选择' : '选择'}${change.kind === 'delete' ? '删除' : ''}${event.title}`); select.setAttribute('aria-pressed', proposalSelection.has(event.id) ? 'true' : 'false')
    select.addEventListener('click', () => { if (proposalSelection.has(event.id)) proposalSelection.delete(event.id); else proposalSelection.add(event.id); renderProposal() })
    selectCell.appendChild(select)
    if (change.kind !== 'delete') row.appendChild(dateCell)
    else row.appendChild(el('td', 'proposal-date-cell'))
    row.appendChild(selectCell)
    body.appendChild(row)
  }
  table.appendChild(body)
  card.appendChild(table)
  const hardIssues = selectedImpact(events, proposalBase).hardIssues
  if (hardIssues.length) {
    const warningText = hardIssues.map(item => `${item.title}（${item.text}）`).join('；')
    card.appendChild(el('div', 'proposal-hard-warning', `硬截止改动需核验：${warningText}`))
    const warning = el('label', 'hard-confirm')
    const check = el('input')
    check.type = 'checkbox'; check.id = 'hard-confirm'
    warning.append(check, el('span', '', '我已核实以上硬截止允许修改或删除，仍要按新日程保存。'))
    card.appendChild(warning)
  }
  const deleteCount = impact.changes.filter(item => item.kind === 'delete' && proposalSelection.has(item.old.id)).length
  card.appendChild(el('div', 'proposal-sub', `已选择 ${proposalSelection.size} 项${deleteCount ? `，其中删除 ${deleteCount} 项` : ''}`))
  const actions = el('div', 'proposal-actions')
  const yes = el('button', 'confirm', calendarState.bulkDeleteAll ? '确认删除所选计划' : '需要，更新计划日历')
  yes.type = 'button'
  yes.disabled = proposalSelection.size === 0
  if (hardIssues.length) {
    yes.disabled = true
    card.querySelector('#hard-confirm').addEventListener('change', event => { yes.disabled = !event.target.checked || proposalSelection.size === 0 })
  }
  yes.addEventListener('click', confirmProposal)
  const no = el('button', 'decline', '不需要改动当前日程表')
  no.type = 'button'
  no.addEventListener('click', declineProposal)
  actions.append(yes, no)
  card.appendChild(actions)
  proposalWrap.appendChild(card)
  chat.appendChild(proposalWrap)
}

function confirmProposal() {
  if (!calendarState.pending) return
  const before = JSON.stringify(calendarState)
  const beforeSelection = new Set(proposalSelection)
  const proposalBase = calendarState.pendingOnlyDelete ? calendarState.bulkDeletePreviousPending || [] : calendarState.confirmed
  const impact = proposalImpact(calendarState.pending, proposalBase)
  const deletedIds = new Set(impact.changes.filter(change => change.kind === 'delete' && proposalSelection.has(change.old.id)).map(change => change.old.id))
  if (!proposalSelection.size) return
  if (selectedImpact(calendarState.pending, proposalBase).hardIssues.length && !document.querySelector('#hard-confirm')?.checked) return
  if (calendarState.pendingOnlyDelete) {
    const remaining = proposalBase.filter(item => !deletedIds.has(item.id))
    calendarState.pending = remaining.length ? remaining : null
    calendarState.changes = remaining.map(item => ({ id: item.id, type: '新增', title: item.title }))
    calendarState.bulkDeleteAll = false
    calendarState.pendingOnlyDelete = false
    calendarState.bulkDeletePreviousPending = null
    calendarState.bulkDeletePreviousChanges = []
    proposalSelection = new Set(remaining.map(item => item.id))
    if (!saveCalendar()) {
      calendarState = JSON.parse(before)
      proposalSelection = beforeSelection
      renderProposal()
      addMessage('error', '本机存储空间不足或不可用，待确认草案未能保存；原日程保持不变。请检查浏览器存储后重试。')
      return
    }
    renderProposal()
    addMessage('assistant', `已撤销所选的 ${deletedIds.size} 项待确认草案；已确认日程没有变化。`)
    return
  }
  const selected = clampProposalDates(calendarState.pending, calendarState.confirmed).filter(event => proposalSelection.has(event.id))
  calendarState.confirmed = dedupeCurrentEvents(calendarState.confirmed.filter(event => !proposalSelection.has(event.id) && !deletedIds.has(event.id)).concat(selected.map(event => ({ ...event }))))
  calendarState.pending = null
  proposalSelection = new Set()
  calendarState.changes = []
  calendarState.bulkDeleteAll = false
  calendarState.pendingOnlyDelete = false
  calendarState.bulkDeletePreviousPending = null
  calendarState.bulkDeletePreviousChanges = []
  if (!saveCalendar()) {
    calendarState = JSON.parse(before)
    proposalSelection = beforeSelection
    renderProposal()
    addMessage('error', '本机存储空间不足或不可用，计划日历未更新；原日程保持不变。请检查浏览器存储后重试。')
    return
  }
  renderProposal()
  renderInAppReminders()
  const firstEvent = calendarState.confirmed.find(event => event.due_date)
  const firstDate = firstEvent?.start_date || firstEvent?.due_date
  if (firstDate) {
    selectedDate = firstDate
    const [year, month] = firstDate.split('-').map(Number)
    viewMonth = new Date(year, month - 1, 1)
  }
  addMessage('assistant', '已按确认内容更新计划日历。你可以继续在聊天中调整，新的改动仍会先请你确认。')
  setTab('calendar')
}

function declineProposal() {
  if (calendarState.bulkDeleteAll) {
    calendarState.pending = calendarState.bulkDeletePreviousPending
    calendarState.changes = calendarState.bulkDeletePreviousChanges
  } else {
    calendarState.pending = null
    calendarState.changes = []
  }
  calendarState.bulkDeleteAll = false
  calendarState.pendingOnlyDelete = false
  calendarState.bulkDeletePreviousPending = null
  calendarState.bulkDeletePreviousChanges = []
  saveCalendar()
  renderProposal()
  addMessage('assistant', '已保留当前日程表，没有应用这次修改。')
}

document.querySelector('#prev-month').addEventListener('click', () => {
  viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1)
  renderCalendar()
})
document.querySelector('#next-month').addEventListener('click', () => {
  viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1)
  renderCalendar()
})

const customModal = document.querySelector('#custom-modal')
const customForm = document.querySelector('#custom-event-form')
const customError = document.querySelector('#custom-error')

function closeCustomModal() {
  customModal.hidden = true
  document.querySelector('#add-custom-event').focus()
}

document.querySelector('#add-custom-event').addEventListener('click', () => {
  customForm.reset()
  customError.textContent = ''
  document.querySelector('#custom-start').value = selectedDate
  document.querySelector('#custom-end').value = selectedDate
  customModal.hidden = false
  document.querySelector('#custom-description').focus()
})
document.querySelector('#cancel-custom').addEventListener('click', closeCustomModal)
customModal.addEventListener('click', event => {
  if (event.target === customModal) closeCustomModal()
})
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !customModal.hidden) closeCustomModal()
})

customForm.addEventListener('submit', event => {
  event.preventDefault()
  const start = document.querySelector('#custom-start').value
  const end = document.querySelector('#custom-end').value
  const description = document.querySelector('#custom-description').value.trim()
  if (!start || !end || !description) {
    customError.textContent = '请填写起始日期、终止日期和事件描述。'
    return
  }
  if (start > end) {
    customError.textContent = '终止日期不能早于起始日期。'
    return
  }
  if (calendarState.confirmed.length >= 40 || (calendarState.pending && calendarState.pending.length >= 40)) {
    customError.textContent = '日程已达到 40 项上限。'
    return
  }
  const id = `m_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
  const firstLine = description.split(/[。！!？?\n]/)[0].trim() || description
  const customEvent = {
    id,
    title: firstLine.slice(0, 80),
    start_date: start,
    due_date: end,
    due_time: null,
    detail: description.length > 80 ? description : '',
    kind: 'task',
    hard_deadline: document.querySelector('#custom-hard').checked,
    date_basis: '用户明确',
    source_note: '用户自定义',
    done: false,
  }
  calendarState.confirmed.push(customEvent)
  if (calendarState.pending) calendarState.pending.push({ ...customEvent })
  if (!saveCalendar()) {
    calendarState.confirmed = calendarState.confirmed.filter(item => item.id !== id)
    if (calendarState.pending) calendarState.pending = calendarState.pending.filter(item => item.id !== id)
    customError.textContent = '本机存储空间不足，日程未保存。'
    return
  }
  selectedDate = start
  const [year, month] = start.split('-').map(Number)
  viewMonth = new Date(year, month - 1, 1)
  closeCustomModal()
  renderCalendar()
  renderProposal()
  renderInAppReminders()
})

function renderCalendar() {
  const year = viewMonth.getFullYear()
  const month = viewMonth.getMonth()
  const hireDate = parseDateValue(userState.profile.start_date)
  document.querySelector('#month-title').textContent = `${year} 年 ${month + 1} 月`
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  const cellCount = Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7
  const grid = document.querySelector('#month-grid')
  grid.replaceChildren()
  for (let i = 0; i < cellCount; i += 1) {
    const day = new Date(year, month, 1 - offset + i)
    const key = dateKey(day)
    const events = calendarState.confirmed.filter(event => visibleOnDate(event, key) && !event.done)
    const hard = calendarState.confirmed.some(event => event.hard_deadline && event.due_date === key)
    const isHireDate = key === hireDate
    const cell = el('button', `day-cell${day.getMonth() !== month ? ' other' : ''}${events.length ? ' has-events' : ''}${key === selectedDate ? ' selected' : ''}${hard ? ' hard-date' : ''}`)
    cell.type = 'button'
    cell.setAttribute('aria-label', `${key}${isHireDate ? '，入职' : ''}，${events.length}项待办${hard ? '，有硬截止' : ''}`)
    cell.appendChild(el('span', 'num', String(day.getDate())))
    if (isHireDate) cell.appendChild(el('span', 'hire-label', '入职'))
    if (events.length) cell.appendChild(el('span', 'hint', events.length === 1 ? events[0].title : `${events.length} 项`))
    cell.addEventListener('click', () => {
      selectedDate = key
      if (day.getMonth() !== month) viewMonth = new Date(day.getFullYear(), day.getMonth(), 1)
      renderCalendar()
      document.querySelector('.calendar-body').scrollTop = 0
    })
    grid.appendChild(cell)
  }
  const [selectedYear, selectedMonth, selectedDay] = selectedDate.split('-').map(Number)
  document.querySelector('#day-title').textContent = `${selectedMonth} 月 ${selectedDay} 日`
  const dayEvents = calendarState.confirmed.filter(event => visibleOnDate(event, selectedDate))
  document.querySelector('#day-count').textContent = `${dayEvents.length} 项`
  renderEventList(document.querySelector('#day-events'), dayEvents, '这一天还没有日程。你可以在助手问答中生成计划。')
  const undated = calendarState.confirmed.filter(event => !event.due_date)
  document.querySelector('#undated-section').hidden = !undated.length
  document.querySelector('#undated-count').textContent = `${undated.length} 项`
  renderEventList(document.querySelector('#undated-events'), undated, '')
}

function renderEventList(container, events, emptyText) {
  container.replaceChildren()
  if (!events.length) {
    if (emptyText) container.appendChild(el('div', 'empty', emptyText))
    return
  }
  for (const event of events) {
    const card = el('article', `event-card${event.done ? ' done' : ''}`)
    const check = el('button', 'event-check', event.done ? '✓' : '')
    check.type = 'button'
    check.setAttribute('aria-label', event.done ? `标记${event.title}未完成` : `标记${event.title}已完成`)
    check.addEventListener('click', () => toggleDone(event.id))
    const main = el('div', 'event-main')
    main.appendChild(el('div', 'event-name', event.title))
    if (event.detail) main.appendChild(el('div', 'event-detail', event.detail))
    appendEventSources(main, event)
    card.append(check, main)
    if (event.id.startsWith('m_')) {
      const remove = el('button', 'event-delete', '删除')
      remove.type = 'button'
      remove.setAttribute('aria-label', `删除自定义日程：${event.title}`)
      remove.addEventListener('click', () => {
        if (remove.dataset.confirm === 'yes') {
          deleteCustomEvent(event.id)
        } else {
          remove.dataset.confirm = 'yes'
          remove.textContent = '确认删除'
        }
      })
      card.appendChild(remove)
    }
    container.appendChild(card)
  }
}

function deleteCustomEvent(id) {
  const beforeConfirmed = calendarState.confirmed
  const beforePending = calendarState.pending
  calendarState.confirmed = beforeConfirmed.filter(item => item.id !== id)
  if (beforePending) calendarState.pending = beforePending.filter(item => item.id !== id)
  if (!saveCalendar()) {
    calendarState.confirmed = beforeConfirmed
    calendarState.pending = beforePending
    document.querySelector('#day-events').prepend(el('div', 'calendar-error', '本机存储空间不足，删除未生效。'))
    return
  }
  renderCalendar()
  renderProposal()
  renderInAppReminders()
}

function toggleDone(id) {
  const item = calendarState.confirmed.find(event => event.id === id)
  if (!item) return
  item.done = !item.done
  if (calendarState.pending) {
    const pendingItem = calendarState.pending.find(event => event.id === id)
    if (pendingItem) pendingItem.done = item.done
  }
  saveCalendar()
  renderCalendar()
  renderProposal()
  renderInAppReminders()
}

function choices(key) {
  return {
    destination_city: ['上海'], company_city: ['上海'], company_district: DISTRICTS,
    employment_type: ['应届生首次就业', '跨城市换工作'], shared_housing: ['是', '否'], pets: ['有', '无'],
  }[key]
}

function selectValue(key, value) {
  if (key === 'destination_city' || key === 'company_city') return value.includes('上海') ? '上海' : value
  if (key === 'shared_housing') return /不接受|不合租|否/.test(value) ? '否' : value ? '是' : ''
  if (key === 'pets') return /没有|无|不养/.test(value) ? '无' : value ? '有' : ''
  if (key === 'employment_type') return /应届|首次/.test(value) ? '应届生首次就业' : /换工作|跳槽/.test(value) ? '跨城市换工作' : value
  return value
}

function parseDateValue(value) {
  // Profile facts extracted from a chat may omit the year (for example,
  // "10月15日").  The backend treats those as dates in the current year, so
  // use the same rule here.  Otherwise opening and saving the picker silently
  // replaces an existing date with today.
  const found = String(value || '').match(/(?:(20\d{2})[-年/.])?(\d{1,2})[-月/.](\d{1,2})日?/)
  if (!found) return ''
  const y = Number(found[1] || shanghaiTodayParts().year), m = Number(found[2]), d = Number(found[3])
  if (m < 1 || m > 12 || d < 1 || d > new Date(y, m, 0).getDate()) return ''
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function makeCityField(wrapper, key, value) {
  const box = el('div', 'cute-dropdown')
  const control = el('input')
  control.type = 'hidden'
  control.name = key
  control.value = value
  const trigger = el('button', 'cute-trigger', value || '请选择目前所在城市')
  trigger.type = 'button'
  trigger.setAttribute('aria-label', '目前所在城市')
  trigger.classList.toggle('has-value', Boolean(value))
  trigger.addEventListener('click', () => openPicker(key, '目前所在城市', control))
  box.append(control, trigger)
  wrapper.appendChild(box)
}

function renderProfile() {
  const fields = document.querySelector('#profile-fields')
  fields.replaceChildren()
  for (const group of PROFILE_GROUPS) {
    const card = el('section', 'profile-group')
    card.appendChild(el('h2', '', group.title))
    for (const [key, label, placeholder] of group.fields) {
      const wrapper = el(key === 'housing_preferences' || key === 'current_city' || choices(key) ? 'div' : 'label', 'profile-field')
      wrapper.appendChild(el('span', '', label))
      const raw = userState.profile[key] || ''
      if (key === 'current_city') makeCityField(wrapper, key, raw)
      else if (key === 'housing_preferences') {
        const box = el('div', 'housing-choices')
        box.dataset.original = raw
        for (const choice of HOUSING_OPTIONS) {
          const item = el('label', 'housing-choice')
          const check = el('input')
          check.type = 'checkbox'; check.name = key; check.value = choice
          check.checked = raw.includes(choice) || (choice === '离地铁口近' && /地铁/.test(raw)) || (choice === '附近有菜市场' && /菜市场/.test(raw)) || (choice === '附近有商场' && /商场/.test(raw)) || (choice === '附近有医院' && /医院/.test(raw))
          check.addEventListener('change', () => { box.dataset.touched = 'true' })
          item.append(check, el('span', '', choice))
          box.appendChild(item)
        }
        wrapper.appendChild(box)
      } else if (key === 'start_date' || key === 'move_deadline' || key === 'commute_preference') {
        const control = el('input', 'picker-input')
        control.name = key; control.readOnly = true; control.value = key === 'commute_preference' ? raw : parseDateValue(raw) || raw
        control.placeholder = '点击滑动选择'
        control.addEventListener('click', () => openPicker(key, label, control))
        wrapper.appendChild(control)
      } else if (choices(key)) {
        const control = el('select')
        control.name = key
        control.appendChild(new Option('请选择', ''))
        for (const choice of choices(key)) control.appendChild(new Option(choice, choice))
        if (key === 'company_district' && !raw) {
          const location = userState.profile.company_location || ''
          control.value = /张江|陆家嘴|金桥/.test(location) ? '浦东新区' : /徐家汇/.test(location) ? '徐汇区' : ''
        } else control.value = selectValue(key, raw)
        if (key === 'company_city' && !raw && (userState.profile.company_location || userState.profile.company_district)) control.value = '上海'
        if (key === 'pets') {
          control.dataset.original = raw
          control.addEventListener('change', () => { control.dataset.touched = 'true' })
        }
        const dropdown = el('div', 'cute-dropdown')
        const trigger = el('button', 'cute-trigger', control.value || '请选择')
        trigger.type = 'button'
        trigger.setAttribute('aria-label', label)
        trigger.setAttribute('aria-expanded', 'false')
        trigger.classList.toggle('has-value', Boolean(control.value))
        const options = el('div', 'cute-options')
        options.hidden = true
        for (const choice of choices(key)) {
          const option = el('button', 'cute-option', choice)
          option.type = 'button'
          option.classList.toggle('selected', control.value === choice)
          option.addEventListener('click', () => {
            control.value = choice
            control.dispatchEvent(new Event('change'))
            trigger.textContent = choice
            trigger.classList.add('has-value')
            options.querySelectorAll('.cute-option').forEach(item => item.classList.toggle('selected', item === option))
            options.hidden = true
            trigger.setAttribute('aria-expanded', 'false')
          })
          options.appendChild(option)
        }
        trigger.addEventListener('click', () => {
          document.querySelectorAll('.cute-options').forEach(list => { if (list !== options) list.hidden = true })
          options.hidden = !options.hidden
          trigger.setAttribute('aria-expanded', String(!options.hidden))
          if (!options.hidden) {
            const selected = options.querySelector('.selected')
            if (selected) options.scrollTop = Math.max(0, selected.offsetTop - 100)
          }
        })
        dropdown.append(control, trigger, options)
        wrapper.appendChild(dropdown)
      } else {
        const control = el(key === 'other_requirements' ? 'textarea' : 'input')
        control.name = key; control.value = raw; control.placeholder = placeholder || ''
        control.maxLength = key === 'other_requirements' ? 1500 : 300
        wrapper.appendChild(control)
      }
      card.appendChild(wrapper)
    }
    fields.appendChild(card)
  }
  const count = PROFILE_FIELDS.filter(key => userState.profile[key]).length
  document.querySelector('#profile-count').textContent = `已记录 ${count} 项资料`
  document.querySelector('#history-count').textContent = `· ${userState.inputs.length} 条`
  const history = document.querySelector('#history-list')
  history.replaceChildren()
  if (!userState.inputs.length) history.appendChild(el('div', 'history-empty', '还没有聊天输入。'))
  for (const item of [...userState.inputs].reverse()) {
    const row = el('div', 'history-item')
    const stamp = item.at ? new Date(item.at) : null
    if (stamp && !Number.isNaN(stamp.getTime())) row.appendChild(el('time', '', stamp.toLocaleString('zh-CN')))
    row.appendChild(el('div', '', item.content))
    history.appendChild(row)
  }
}

function renderReminderSettings() {
  const settings = userState.reminders
  document.querySelector('#reminder-in-app').checked = settings.inApp
  document.querySelector('#reminder-wechat').checked = settings.wechat
  document.querySelector('#reminder-three-days').value = settings.threeDays
  document.querySelector('#reminder-due-day').value = settings.dueDay
  const list = document.querySelector('#reminder-status-list')
  list.replaceChildren()
  const upcoming = calendarState.confirmed.filter(event => !event.done && event.due_date && event.due_date >= shanghaiTodayKey()).sort((a, b) => a.due_date.localeCompare(b.due_date)).slice(0, 3)
  if (!upcoming.length) list.appendChild(el('div', 'reminder-status-empty', '暂无待提醒的计划'))
  for (const event of upcoming) {
    const row = el('div', 'reminder-status-row')
    row.append(el('span', '', `${event.due_date.slice(5).replace('-', ' 月 ')} 日`), el('strong', '', event.title), el('em', settings.inApp ? '站内已开启' : settings.wechat ? '微信未接入' : '未开启'))
    list.appendChild(row)
  }
}

function openReminderSettings() {
  document.querySelector('.profile-body').hidden = true
  document.querySelector('#reminder-settings').hidden = false
  renderReminderSettings()
}

function openReminderTimePicker(control, title) {
  const columns = document.querySelector('#picker-columns')
  columns.replaceChildren()
  const selected = REMINDER_TIMES.includes(control.value) ? control.value : '09:00'
  pickerState = { key: 'reminder_time', control, values: [Math.max(0, REMINDER_TIMES.indexOf(selected))] }
  document.querySelector('#picker-title').textContent = title
  document.querySelector('#picker-search-wrap').hidden = true
  document.querySelector('#picker-city-labels').hidden = true
  buildWheel(columns, REMINDER_TIMES, 0, value => value)
  document.querySelector('#profile-picker').hidden = false
  requestAnimationFrame(() => { const column = columns.querySelector('.wheel-column'); if (column) column.scrollTop = Number(column.dataset.index) * 42 })
}

function closeReminderSettings() {
  document.querySelector('#reminder-settings').hidden = true
  document.querySelector('.profile-body').hidden = false
}

function openPicker(key, title, control) {
  const modal = document.querySelector('#profile-picker')
  const columns = document.querySelector('#picker-columns')
  columns.replaceChildren()
  document.querySelector('#picker-title').textContent = title
  const searchWrap = document.querySelector('#picker-search-wrap')
  searchWrap.hidden = key !== 'current_city'
  document.querySelector('#picker-city-labels').hidden = key !== 'current_city'
  document.querySelector('#picker-search').value = ''
  document.querySelector('#picker-search-results').hidden = true
  if (key === 'current_city') {
    const match = cityOptions.find(item => item.city === control.value || item.city.replace(/市$/, '') === control.value)
    pickerState = { key, control, province: match?.province || cityOptions[0]?.province || '', city: match?.city || cityOptions[0]?.city || '' }
    renderCityColumns()
    modal.hidden = false
    return
  }
  const date = parseDateValue(control.value) || shanghaiTodayKey()
  const [year, month, day] = date.split('-').map(Number)
  pickerState = { key, control, values: key === 'commute_preference' ? [Math.max(0, COMMUTE.indexOf(control.value))] : [year, month, day] }
  if (key === 'commute_preference') buildWheel(columns, COMMUTE, 0, value => value)
  else {
    buildWheel(columns, Array.from({ length: 41 }, (_, i) => 2020 + i), 0, value => `${value}年`)
    buildWheel(columns, Array.from({ length: 12 }, (_, i) => i + 1), 1, value => `${value}月`)
    buildDayWheel(columns)
  }
  modal.hidden = false
  requestAnimationFrame(() => columns.querySelectorAll('.wheel-column').forEach(column => column.scrollTop = Number(column.dataset.index) * 42))
}

function renderCityColumns() {
  const columns = document.querySelector('#picker-columns')
  columns.replaceChildren()
  const provinces = [...new Set(cityOptions.map(item => item.province))]
  const cities = cityOptions.filter(item => item.province === pickerState.province).map(item => item.city)
  if (!provinces.length) {
    columns.appendChild(el('div', 'city-no-match', '城市数据加载中，请稍后重试。'))
    return
  }
  if (!cities.includes(pickerState.city)) pickerState.city = cities[0]
  for (const [part, values, selected] of [[0, provinces, pickerState.province], [1, cities, pickerState.city]]) {
    const column = el('div', 'wheel-column city-wheel')
    column.dataset.part = String(part)
    column.setAttribute('role', 'listbox')
    column.setAttribute('aria-label', part === 0 ? '省份' : '城市')
    for (const [index, value] of values.entries()) {
      const option = el('button', 'wheel-option', value)
      option.type = 'button'
      option.addEventListener('click', () => {
        if (part === 0) chooseCityWheel(part, value)
        else { column.scrollTop = index * 42; chooseCityWheel(part, value) }
      })
      column.appendChild(option)
    }
    let timer
    column.addEventListener('scroll', () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        if (column.isConnected) chooseCityWheel(part, values[Math.min(values.length - 1, Math.max(0, Math.round(column.scrollTop / 42)))])
      }, 70)
    })
    columns.appendChild(column)
    requestAnimationFrame(() => { if (column.isConnected) column.scrollTop = Math.max(0, values.indexOf(selected)) * 42 })
  }
}

function chooseCityWheel(part, value) {
  if (!pickerState || pickerState.key !== 'current_city' || !value) return
  if (part === 0 && pickerState.province !== value) {
    pickerState.province = value
    pickerState.city = cityOptions.find(item => item.province === value)?.city || ''
    renderCityColumns()
  } else if (part === 1) pickerState.city = value
}

document.querySelector('#picker-search').addEventListener('input', event => {
  if (!pickerState || pickerState.key !== 'current_city') return
  const results = document.querySelector('#picker-search-results')
  const query = event.target.value.trim().toLowerCase()
  results.replaceChildren()
  results.hidden = !query
  if (!query) return
  const matches = cityOptions.filter(item => `${item.province}${item.city}`.toLowerCase().includes(query)).slice(0, 30)
  for (const item of matches) {
    const option = el('button', 'cute-option', `${item.province} · ${item.city}`)
    option.type = 'button'
    option.addEventListener('click', () => {
      pickerState.province = item.province
      pickerState.city = item.city
      renderCityColumns()
      event.target.value = ''
      results.hidden = true
    })
    results.appendChild(option)
  }
  if (!matches.length) results.appendChild(el('div', 'city-no-match', '没有匹配的城市'))
})

function buildDayWheel(container) {
  const [year, month, day] = pickerState.values
  const limit = new Date(year, month, 0).getDate()
  pickerState.values[2] = Math.min(day, limit)
  container.querySelector('.wheel-column[data-part="2"]')?.remove()
  buildWheel(container, Array.from({ length: limit }, (_, i) => i + 1), 2, value => `${value}日`)
  requestAnimationFrame(() => { const column = container.querySelector('.wheel-column[data-part="2"]'); if (column) column.scrollTop = Number(column.dataset.index) * 42 })
}

function buildWheel(container, values, part, label) {
  const column = el('div', 'wheel-column')
  column.dataset.part = String(part)
  column.dataset.index = String(Math.max(0, values.indexOf(pickerState.values[part])))
  column.setAttribute('role', 'listbox')
  for (const [index, value] of values.entries()) {
    const option = el('button', 'wheel-option', label(value))
    option.type = 'button'
    option.addEventListener('click', () => { column.scrollTo({ top: index * 42, behavior: 'smooth' }); choose(index) })
    column.appendChild(option)
  }
  const choose = index => {
    const next = Math.min(values.length - 1, Math.max(0, index))
    if (pickerState.values[part] === values[next]) return
    pickerState.values[part] = values[next]
    column.dataset.index = String(next)
    if (part < 2 && pickerState.key !== 'commute_preference') buildDayWheel(container)
  }
  let timer
  column.addEventListener('scroll', () => {
    clearTimeout(timer)
    timer = setTimeout(() => choose(Math.round(column.scrollTop / 42)), 60)
  })
  container.appendChild(column)
}

function closePicker() {
  document.querySelector('#profile-picker').hidden = true
  pickerState = null
}

document.querySelector('#picker-cancel').addEventListener('click', closePicker)
document.querySelector('#picker-confirm').addEventListener('click', () => {
  if (!pickerState) return
  if (pickerState.key === 'current_city') {
    if (!pickerState.city) return
    const provinces = [...new Set(cityOptions.map(item => item.province))]
    const provinceColumn = document.querySelector('.city-wheel[data-part="0"]')
    const province = provinces[Math.round(provinceColumn.scrollTop / 42)] || pickerState.province
    const cities = cityOptions.filter(item => item.province === province).map(item => item.city)
    const cityColumn = document.querySelector('.city-wheel[data-part="1"]')
    const city = province === pickerState.province ? cities[Math.round(cityColumn.scrollTop / 42)] || pickerState.city : cities[0]
    pickerState.control.value = city
    const trigger = pickerState.control.closest('.cute-dropdown').querySelector('.cute-trigger')
    trigger.textContent = city
    trigger.classList.add('has-value')
    closePicker()
    return
  }
  const columns = [...document.querySelectorAll('#picker-columns .wheel-column')]
  if (pickerState.key === 'reminder_time') {
    const column = columns[0]
    const index = column ? Math.min(REMINDER_TIMES.length - 1, Math.max(0, Math.round(column.scrollTop / 42))) : 4
    pickerState.control.value = REMINDER_TIMES[index]
    closePicker()
    return
  }
  for (const column of columns) {
    const part = Number(column.dataset.part)
    const index = Math.round(column.scrollTop / 42)
    pickerState.values[part] = part === 0 && pickerState.key !== 'commute_preference' ? 2020 + index : part === 1 ? 1 + index : part === 2 ? 1 + index : index
  }
  const { key, control, values } = pickerState
  const selectedDate = `${values[0]}-${String(values[1]).padStart(2, '0')}-${String(Math.min(values[2], new Date(values[0], values[1], 0).getDate())).padStart(2, '0')}`
  if (key === 'proposal_date') pickerState.onConfirm(selectedDate)
  else control.value = key === 'commute_preference' ? COMMUTE[values[0]] : selectedDate
  closePicker()
})
document.querySelector('#profile-picker').addEventListener('click', event => { if (event.target.id === 'profile-picker') closePicker() })
document.querySelector('#profile-menu-button').addEventListener('click', () => {
  const menu = document.querySelector('#profile-menu')
  menu.hidden = !menu.hidden
  document.querySelector('#history-panel').hidden = true
  document.querySelector('#open-history').hidden = false
  document.querySelector('#profile-menu-button').setAttribute('aria-expanded', String(!menu.hidden))
})
document.querySelector('#open-history').addEventListener('click', () => {
  document.querySelector('#open-history').hidden = true
  document.querySelector('#history-panel').hidden = false
})
document.querySelector('#back-history').addEventListener('click', () => {
  document.querySelector('#history-panel').hidden = true
  document.querySelector('#open-history').hidden = false
})
document.addEventListener('click', event => {
  if (!event.target.closest('.profile-hero')) {
    document.querySelector('#profile-menu').hidden = true
    document.querySelector('#profile-menu-button').setAttribute('aria-expanded', 'false')
  }
})
fetch('/china_cities.json').then(response => response.json()).then(data => { cityOptions = data.cities || [] }).catch(() => { cityOptions = [] })

document.querySelector('#profile-form').addEventListener('submit', event => {
  event.preventDefault()
  const form = event.currentTarget
  const next = {}
  for (const key of PROFILE_FIELDS) {
    const value = key === 'housing_preferences'
      ? (form.querySelector('.housing-choices').dataset.touched
        ? [...form.querySelectorAll('input[name="housing_preferences"]:checked')].map(item => item.value).join('、')
        : form.querySelector('.housing-choices').dataset.original)
      : key === 'pets' && !form.elements.namedItem(key).dataset.touched
        ? form.elements.namedItem(key).dataset.original || form.elements.namedItem(key).value.trim()
        : form.elements.namedItem(key).value.trim()
    if (value) next[key] = value
  }
  if (next.current_city && cityOptions.length && !cityOptions.some(item => item.city === next.current_city || item.city.replace(/市$/, '') === next.current_city)) {
    document.querySelector('#profile-status').textContent = '请从搜索结果中选择目前所在城市。'
    return
  }
  if (!next.company_city && (next.company_district || next.company_location)) next.company_city = '上海'
  userState.profile = next
  userState.updatedAt = new Date().toISOString()
  updateIntro()
  renderOnboarding()
  const saved = saveUserState()
  renderProfile()
  if (saved) document.querySelector('#profile-status').textContent = '资料已保存，下次问答会自动使用。'
})

document.querySelector('#open-reminders').addEventListener('click', openReminderSettings)
document.querySelector('#back-reminders').addEventListener('click', closeReminderSettings)
document.querySelector('#save-reminders').addEventListener('click', () => {
  userState.reminders = {
    inApp: document.querySelector('#reminder-in-app').checked,
    wechat: document.querySelector('#reminder-wechat').checked,
    threeDays: document.querySelector('#reminder-three-days').value || '09:00',
    dueDay: document.querySelector('#reminder-due-day').value || '08:30',
  }
  saveUserState()
  renderReminderSettings()
  renderInAppReminders()
  document.querySelector('#save-reminders').textContent = '已保存'
  setTimeout(() => { const button = document.querySelector('#save-reminders'); if (button) button.textContent = '保存提醒设置' }, 1200)
})
document.querySelector('#reminder-three-days').addEventListener('click', event => openReminderTimePicker(event.currentTarget, '任务到期前 3 天'))
document.querySelector('#reminder-due-day').addEventListener('click', event => openReminderTimePicker(event.currentTarget, '任务到期当天'))

document.querySelector('#clear-user-data').addEventListener('click', () => {
  if (!window.confirm('确定清空资料、聊天记录和提醒偏好吗？已确认的计划日历会保留。')) return
  localStorage.removeItem(USER_KEY)
  window.location.reload()
})

window.addEventListener('storage', event => {
  if (event.key === STORAGE_KEY) {
    calendarState = loadCalendar()
    renderCalendar()
    renderProposal()
  } else if (event.key === USER_KEY) {
    const current = loadUserState()
    messages.splice(0, messages.length, ...current.conversation)
    userState.profile = current.profile
    userState.inputs = current.inputs
    userState.reminders = current.reminders
    userState.updatedAt = current.updatedAt
    userState.onboardingDone = current.onboardingDone
    updateIntro()
    renderOnboarding()
    if (!document.querySelector('#profile-view').hidden) renderProfile()
  }
})

for (const message of messages.slice(-40)) {
  const row = addMessage(message.role, message.content, message.evidence || [], message.sources || [])
  if (message.role === 'assistant') attachFeedback(row, message)
}
updateIntro()
renderOnboarding()
renderInAppReminders()
renderCalendar()
renderProposal()
if (calendarState.bulkDeleteAll) requestAnimationFrame(showProposalStart)
