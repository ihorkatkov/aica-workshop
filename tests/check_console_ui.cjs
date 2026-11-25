// Render the actual console script against synthetic states without a browser or live CRM writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('crm/console.html', 'utf8');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value: id === 'filter' ? 'all' : '', textContent: '', innerHTML: '', classList: {toggle() {}}});
  return elements.get(id);
};
const context = vm.createContext({document: {querySelector: () => ({content: 'test'}), getElementById: element, querySelectorAll: () => []}, fetch: () => new Promise(() => {})});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const deal = {id:'D-101',title:'Customer <one>',stage:'pilot_requested',security_review:'open',kickoffs:0,review_requests:0,notes:'Phone confirmation',revision:1};
const state = {deals:[deal],proposals:[],audit:[]};
function render() {context.fixture = state; vm.runInContext('data=fixture; render()', context); return element('detail').innerHTML;}
let detail = render();
assert.match(detail, /Customer &lt;one&gt;/);
assert.match(detail, /Pilot requested/);
assert.match(detail, /Phone confirmation/);
assert.doesNotMatch(detail, /[Pp]roposal|[Aa]pprov|[Pp]romot|duplicate|guardrail/);
state.audit.push({id:1,event:'unsafe_write',detail:{deal_id:'D-101',action:'schedule_kickoff'}});
detail=render();
assert.match(detail, /Kickoff scheduled/);
assert.match(detail, /<small>Agent<\/small>/);
assert.doesNotMatch(detail, /unsafe|no approval/);
state.proposals.push({id:'p1',deal_id:'D-101',action:'schedule_kickoff',status:'pending',revision:1});
detail=render();
assert.match(detail, /data-action="approve"/);
assert.doesNotMatch(detail, /data-action="promote"/);
state.proposals[0].status='approved';
assert.match(render(), /data-action="promote"/);
state.proposals[0].status='applied';
assert.doesNotMatch(render(), /data-action/);
element('search').value='unmatched';
assert.match(render(), /No deal selected/);
element('search').value='';element('filter').value='cleared';
assert.match(render(), /No deal selected/);
assert.doesNotMatch(html, /Try before approval|Verify no duplicate|Exercise controls|You decide what goes live/);
console.log('Console rendering checks passed: baseline, activity, proposal states, search, filter, escaping.');

// Sorting must preserve numerical order, and record navigation must preserve list inputs.
element('filter').value='all';
state.deals.push({...deal,id:'D-102',title:'Another customer / Rotterdam',kickoffs:12});
vm.runInContext("sortKey='kickoffs';sortDirection=-1;selected='D-101';recordOpen=true;activeTab='activity'",context);
detail=render();
assert.equal(element('list-view').hidden,true);
assert.equal(element('record-view').hidden,false);
assert.ok(element('deals').innerHTML.indexOf('D-102') < element('deals').innerHTML.indexOf('D-101'));
assert.match(detail,/id="panel-activity"[^>]*aria-labelledby="tab-activity" >/);
assert.match(detail,/id="panel-details"[^>]*hidden/);
element('search').value='Customer';
vm.runInContext('openList()',context);
assert.equal(element('search').value,'Customer');
assert.equal(element('list-view').hidden,false);
assert.equal(element('record-view').hidden,true);
state.proposals=[];
vm.runInContext("activeTab='proposals'",context);
render();
assert.equal(vm.runInContext('activeTab',context),'activity');
console.log('Table sorting, record/list navigation, tab visibility and conditional proposals passed.');

// Refresh must not replace an open record just because it stops matching the list filter.
element('search').value='';element('filter').value='cleared';
state.deals[0].security_review='open';
vm.runInContext("recordOpen=true;selected='D-101'",context);
detail=render();
assert.match(detail,/Deal · D-101/);
assert.equal(vm.runInContext('selected',context),'D-101');
state.proposals=[{id:'p2',deal_id:'D-101',action:'schedule_kickoff',status:'pending',revision:1}];
element('filter').value='all';render();
assert.match(element('deals').innerHTML,/1 awaiting action/);
console.log('Open-record refresh identity and contextual proposal indicator passed.');

// Completed requests belong only in history; no proposal card, tab, or raw counter preview.
state.proposals=[{id:'done',deal_id:'D-101',action:'request_review_update',status:'applied',revision:1}];
state.audit.push({id:2,event:'promoted',detail:{deal_id:'D-101',proposal_id:'done',changed:true}});
vm.runInContext("activeTab='activity'",context);
detail=render();
assert.match(detail,/Security review requested/);
assert.doesNotMatch(detail,/class="proposal"|panel-proposals|tab-proposals|Current record:|Requested change:|Pending requests/);
state.proposals[0].status='pending';
detail=render();
assert.match(detail,/Pending requests/);
assert.match(detail,/Request a security review/);
assert.match(detail,/data-action="approve"/);
assert.doesNotMatch(detail,/tab-proposals|Current record:|Requested change:/);
console.log('Business activity and pending-request presentation passed.');
