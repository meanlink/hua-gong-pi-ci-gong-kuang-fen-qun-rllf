import {jobs} from '../api/entities.js';
import {heading} from '../components/common/shell.js';
import {status} from '../components/common/status.js';
import {esc,date} from '../utils/dom.js';
const STATUS_TEXT={queued:'排队中',running:'计算中',completed:'已完成',failed:'执行失败',canceled:'已停止/撤销'};
function short(fp){return fp?fp.slice(0,12)+'…':'';}
export async function sharing(){
 const comps=await jobs.computations();
 const cards=comps.length?comps.map(c=>{
  const waiters=c.waiting_jobs||[];
  const failed=c.status==='failed';
  return '<article class="panel share-card"><div class="section-title"><h2>共享计算 #'+c.id+' · 第'+c.epoch+'代</h2>'+status(c.status)+'</div><p class="hint">复用指纹（数据内容+分群参数，与行序无关）：<code>'+esc(short(c.fingerprint))+'</code> · 参数 <code>'+esc(JSON.stringify(c.params))+'</code></p><p class="hint">创建 '+date(c.created_at)+(c.finished_at?' · 结束 '+date(c.finished_at):'')+'</p>'+(failed?'<p class="warning">失败原因：'+esc(c.error||'未提供')+'（失败结果不缓存，再建会另开新计算）</p>':'')+'<div class="section-title"><h3>等待与复用关系（'+waiters.length+' 份分析）</h3></div><table class="share-table"><thead><tr><th>分析</th><th>状态</th><th>复用来源</th><th>撤销</th><th></th></tr></thead><tbody>'+waiters.map(w=>'<tr><td>'+esc(w.name)+' <small>#'+w.id+'</small></td><td>'+esc(STATUS_TEXT[w.status]||w.status)+'</td><td>'+(w.reused_from_job_id?'复用自 #'+esc(w.reused_from_job_id):'—')+'</td><td>'+(w.canceled?'已撤销':'有效')+'</td><td><a class="text-button" href="#/results/'+w.id+'">查看 ↗</a></td></tr>').join('')+'</tbody></table></article>';
 }).join(''):'<div class="empty">尚无共享计算。到分析工作台提交一次分析后，这里会展示复用来源、等待关系与失败原因。</div>';
 return heading('05 / SHARED COMPUTE','共享计算与等待关系','内容相同（行序不同不影响）且分群参数一致的分析共用一份计算；各分析保留独立名称、批准与分发。失败不缓存，全撤销即停，代次隔离迟到结果。','<button class="button" id="refresh-sharing">刷新 ↻</button>')+'<div class="share-grid">'+cards+'</div>';
}
export function bindSharing(refresh){document.querySelector('#refresh-sharing')?.addEventListener('click',refresh);}
