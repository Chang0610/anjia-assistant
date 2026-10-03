const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, '..', 'preview', 'app.js'), 'utf8')
const functionText = (name, nextName) => source.slice(source.indexOf(`function ${name}(`), source.indexOf(`function ${nextName}(`))
const sandbox = {
  calendarState: { confirmed: [], changes: [] },
  userState: { onboardingDone: false, profile: {} },
  messages: [],
  shanghaiTodayKey: () => '2026-10-02',
}
vm.createContext(sandbox)
vm.runInContext(functionText('returningWelcomeText', 'updateIntro') + functionText('needsOnboarding', 'onboardingInput'), sandbox)

assert.equal(sandbox.needsOnboarding(), true)
sandbox.userState.onboardingDone = true
assert.equal(sandbox.needsOnboarding(), false)
assert.match(sandbox.returningWelcomeText(), /当前进度：0 \/ 0/)
assert.match(sandbox.returningWelcomeText(), /要根据已保存的信息生成计划吗？/)

sandbox.calendarState.confirmed = [
  { title: '到岗入职', due_date: '2026-10-15', done: false },
  { title: '完成搬家', due_date: '2026-10-10', done: false },
  { title: '核对旧住处退租', due_date: '2026-10-03', done: true },
  { title: '签订租约', due_date: '2026-10-08', done: false },
  { title: '开通宽带', due_date: '2026-10-11', done: false },
]
sandbox.calendarState.changes = [{}, {}]
const welcome = sandbox.returningWelcomeText()
assert.match(welcome, /当前进度：1 \/ 5（已完成 \/ 总任务）/)
assert.match(welcome, /先核对2项待确认的日程改动/)
assert.ok(welcome.indexOf('签订租约（10-08）') < welcome.indexOf('完成搬家（10-10）'))
assert.ok(welcome.indexOf('完成搬家（10-10）') < welcome.indexOf('开通宽带（10-11）'))
assert.ok(!welcome.includes('到岗入职（10-15）'))
assert.ok((welcome.match(/[？?]/g) || []).length <= 3)
console.log('returning welcome shows confirmed progress and the next three tasks; first-time onboarding remains available')
