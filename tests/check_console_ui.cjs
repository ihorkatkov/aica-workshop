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
state.audit.push({id:1,event:'unsafe_write',detail:{deal_id:'D-101',action:'schedule_kickoff'}});
detail=render();
assert.match(detail, /Kickoff scheduled/);
assert.match(detail, /<small>Agent<\/small>/);
assert.doesNotMatch(detail, /unsafe|no approval/);
element('search').value='unmatched';
assert.match(render(), /No deal selected/);
element('search').value='';element('filter').value='cleared';
assert.match(render(), /No deal selected/);
console.log('Console rendering checks passed: baseline, activity, search, filter, escaping.');

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
console.log('Table sorting, record/list navigation, tab visibility passed.');

// Refresh must not replace an open record just because it stops matching the list filter.
element('search').value='';element('filter').value='cleared';
state.deals[0].security_review='open';
vm.runInContext("recordOpen=true;selected='D-101'",context);
detail=render();
assert.match(detail,/Deal · D-101/);
assert.equal(vm.runInContext('selected',context),'D-101');

element('filter').value='all';
state.proposals=[{id:'old',deal_id:'D-101',action:'schedule_kickoff',status:'pending'}];
state.audit.push({id:2,event:'proposed',detail:{deal_id:'D-101',proposal_id:'old'}});
state.audit.push({id:3,event:'deal_updated',detail:{deal_id:'D-101',action:'request_review_update',after:{review_requests:1}}});
detail=render();
assert.match(detail,/Security review requested/);
assert.match(detail,/Review requests: 1/);
console.log('Activity shows the recorded review request.');

assert.match(detail,/Request security review/);
assert.match(detail,/Update review status/);
assert.match(detail,/Schedule kickoff/);
state.audit.push({id:4,event:'deal_updated',detail:{deal_id:'D-101',action:'schedule_kickoff',actor:'human',after:{kickoffs:1}}});
state.audit.push({id:5,event:'review_changed',detail:{deal_id:'D-101',actor:'human',previous_status:'open',status:'cleared',valid_until:'2027-03-31'}});
detail=render();
assert.match(detail,/Human · Kickoff meetings: 1/);
assert.match(detail,/Human · Open → Cleared · Valid through 2027-03-31/);
assert.match(detail,/sets the review to Open and clears its previous validity date/);
state.audit.push({id:6,event:'deal_updated',detail:{deal_id:'D-101',action:'request_review_update',actor:'human',before:{security_review:'cleared'},after:{review_requests:2,security_review:'open',review_valid_until:null}}});
detail=render();
assert.match(detail,/Human · Review requests: 2 · Review: Cleared → Open/);
console.log('Direct business actions and Human activity attribution passed.');

state.proposals = [];
vm.runInContext("queueOpen=true;render()", context);
assert.match(element('queue-body').innerHTML, /No stage proposals awaiting review/);
state.proposals = [{id:'p1',deal_id:deal.id,from_stage:'pilot',to_stage:'rollout',rationale:'Capacity <uncertain>',status:'pending'}];
vm.runInContext('render()', context);
assert.match(element('queue-body').innerHTML, /Approve Rollout/);
assert.match(element('queue-body').innerHTML, /Capacity &lt;uncertain&gt;/);
assert.match(element('queue-body').innerHTML, /Customer evidence/);
assert.match(element('queue-body').innerHTML, /Edit proposal/);
assert.match(element('queue-body').innerHTML, /Reject/);
state.proposals[0].status='approved';
vm.runInContext('render()', context);
assert.match(element('queue-body').innerHTML, /No stage proposals awaiting review/);
state.audit.push({id:7,event:'stage_decided',detail:{deal_id:deal.id,status:'approved',from_stage:'pilot',proposed_to_stage:'rollout',to_stage:'rollout_planning'}});
vm.runInContext("queueOpen=false;selected='D-101';recordOpen=true;activeTab='activity';render()",context);
assert.match(element('detail').innerHTML,/Agent proposed Rollout · Owner approved Rollout planning/);
console.log('Stage queue, rationale escaping and edited decision history passed.');
state.proposals[0].status = 'pending';
state.proposals[0].from_stage = 'pilot';
deal.stage = 'rollout';
vm.runInContext('queueOpen=true;render()',context);
assert.match(element('queue-body').innerHTML, /deal has changed/);
assert.match(element('queue-body').innerHTML, /disabled data-approve/);
assert.match(element('queue-body').innerHTML, /disabled data-edit/);
assert.doesNotMatch(element('queue-body').innerHTML, /disabled data-reject/);
