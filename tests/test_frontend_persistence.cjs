const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, '..', 'preview', 'app.js'), 'utf8')
const functionText = (name, nextName) => source.slice(source.indexOf(`function ${name}(`), source.indexOf(`function ${nextName}(`))
const calendar = {
  confirmed: [], pending: [{ id: 'draft', title: '搬入新住所', due_date: '2026-10-17', date_basis: '建议日期' }],
  changes: [{ id: 'draft', type: '新增' }], bulkDeleteAll: false, pendingOnlyDelete: false,
  bulkDeletePreviousPending: null, bulkDeletePreviousChanges: [],
}
const messages = []
const sandbox = {
  STORAGE_KEY: 'test-calendar', JSON, Set, Date,
  calendarState: calendar, proposalSelection: new Set(['draft']),
  localStorage: { setItem() { throw new Error('QuotaExceededError') } },
  proposalImpact: () => ({ changes: [{ kind: 'add', next: calendar.pending[0] }] }),
  selectedImpact: () => ({ hardIssues: [] }),
  clampProposalDates: events => events,
  dedupeCurrentEvents: events => events,
  renderProposal() {},
  addMessage: (...args) => messages.push(args),
}
vm.createContext(sandbox)
vm.runInContext(functionText('saveCalendar', 'el') + functionText('confirmProposal', 'declineProposal'), sandbox)
vm.runInContext('confirmProposal()', sandbox)
assert.equal(sandbox.calendarState.confirmed.length, 0)
assert.equal(sandbox.calendarState.pending.length, 1)
assert.equal(sandbox.proposalSelection.has('draft'), true)
assert.equal(messages.length, 1)
assert.equal(messages[0][0], 'error')
assert.match(messages[0][1], /计划日历未更新/)
console.log('calendar confirmation rolls back when browser storage fails')
