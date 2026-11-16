import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
function waitingHint(j){
 if(j.status==='completed'&&j.reused_from_job_id)return '<span class="badge reuse" title="结果复用自已成功的共享计算">复用自分析 #'+esc(j.reused_from_job_id)+'</span>';
 if(j.status==='queued'&&j.computation_id)return '<span class="badge share" title="多个同内容同参数分析共享同一份后台计算">共享计算 #'+esc(j.computation_id)+' 等待中</span>';
 if(j.computation_id)return '<span class="badge share">共享计算 #'+esc(j.computation_id)+'</span>';
 return '';
}
export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 const canCancel=session.user.role!=='viewer'&&['queued','running'].includes(j.status)&&!j.canceled;
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button><a class="button" href="#/sharing">共享计算视图 ↗</a>')+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+waitingHint(j)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(j.approved?'已获业务批准':'待负责人复核')+'</span>'+(canCancel?'<button class="button small danger" id="cancel-job">撤销此等待分析</button>':'')+'</div>'+(j.status==='completed'?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(session.user.role==='admin'&&!j.approved?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+'<p class="hint">仅批准结果可进入定时分发档案。</p></section></div><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':j.status==='failed'?'<section class="panel empty"><p class="eyebrow">FAILURE REASON</p><h2>计算失败</h2><p class="warning">'+esc(j.error||'未提供失败原因')+'</p><p class="hint">失败结果不会缓存：调整参数或数据后重新创建，将启动一份新的计算。</p><a class="button" href="#/workbench">返回工作台 ↗</a></section>':j.status==='canceled'?'<section class="panel empty"><h2>该分析已撤销</h2><p>撤销保持有效，不会被后续共享计算补齐；同内容的其他分析不受影响。</p><a class="button" href="#/sharing">查看共享计算视图 ↗</a></section>':'<section class="panel empty">后台正在执行共享计算。点击刷新结果查看最新进展。<a href="#/workbench">返回工作台 ↗</a></section>');
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});document.querySelector('#cancel-job')?.addEventListener('click',async()=>{try{await jobs.cancel(workspace.selectedJob);notify('已撤销；若该计算无其他等待者，后台将停止计算');await refresh();}catch(e){notify(e.message,true);}});}
