<template>
  <main class="app-shell" :class="{ expanded: isExpanded }">
    <div v-if="!isExpanded" class="hero">
      <div class="hero-icon"><svg viewBox="0 0 24 24"><path d="M12 2.5c-.7 0-1.4.2-2 .6L4.6 7C3.6 7.6 3 8.7 3 9.9v4.2c0 1.2.6 2.3 1.6 2.9l5.4 3.9c1.2.8 2.8.8 4 0l5.4-3.9c1-.7 1.6-1.7 1.6-2.9V9.9c0-1.2-.6-2.3-1.6-2.9L14 3.1a3.6 3.6 0 0 0-2-.6Z"/></svg></div>
      <h1>DeepResearch</h1>
      <p class="hero-sub">AI 驱动的深度研究助手</p>
      <form class="hero-form" @submit.prevent="handleSubmit">
        <textarea v-model="form.topic" class="hero-input" placeholder="输入你想深入研究的话题..." rows="2" required></textarea>
        <div class="hero-row">
          <select v-model="form.searchApi" class="hero-select"><option value="">搜索引擎（沿用后端配置）</option><option v-for="o in searchOptions" :key="o.value" :value="o.value">{{ o.label }}</option></select>
          <button class="btn btn-primary" type="submit" :disabled="loading"><svg v-if="loading" class="spinner" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke-width="3"/></svg>{{ loading?'研究中...':'开始研究' }}</button>
          <button v-if="loading" type="button" class="btn btn-secondary" @click="cancelResearch">取消</button>
        </div>
      </form>
      <div class="upload-zone"><label class="upload-label"><input type="file" accept=".pdf,.docx,.md,.txt" @change="handleUpload" :disabled="uploading" style="display:none" ref="fileInput"/><span class="upload-hint">{{ uploading?'上传中...':'点击上传知识库文件（PDF/DOCX/MD/TXT）' }}</span></label><p v-if="uploadMsg" class="upload-msg">{{ uploadMsg }}</p><p class="kb-stats" v-if="kbStats">知识库已有 {{ kbStats }} 个文本块</p></div>
      <p v-if="error" class="error-msg">{{ error }}</p>
      <div class="history-section" v-if="history.length"><h3>研究历史</h3><ul><li v-for="h in history" :key="h.id" @click="loadHistoryDetail(h.id)"><span class="hist-topic">{{ h.topic }}</span><span class="hist-date">{{ new Date(h.created_at*1000).toLocaleDateString('zh') }}</span></li></ul><div v-if="historyDetail" class="history-detail"><div class="hist-detail-head"><h4>{{ historyDetail.topic }}</h4><button class="btn btn-secondary btn-sm" @click="historyDetail=null">关闭</button></div><div class="md" v-html="renderMd(historyDetail.report_markdown||'暂无内容')"></div></div></div>
    </div>

    <div v-else class="workspace">
      <aside class="sidebar">
        <div class="side-head"><button class="btn btn-secondary btn-sm" @click="goBack" :disabled="loading">返回</button><h2>DeepResearch</h2></div>
        <div class="side-topic"><label>研究主题</label><p>{{ form.topic }}</p></div>
        <div class="side-info"><div class="info-row" v-if="activeSkill"><label>技能</label><span class="tag skill-tag">{{ activeSkill }}</span></div><div class="info-row" v-if="totalTasks"><label>进度</label><div class="mini-bar"><div class="mini-fill" :style="{width:(completedTasks/totalTasks)*100+'%'}"></div></div><span>{{ completedTasks }}/{{ totalTasks }}</span></div></div>
        <div class="side-tasks" v-if="todoTasks.length"><h3>任务清单</h3><ul><li v-for="t in todoTasks" :key="t.id" :class="{active:t.id===activeTaskId, done:t.status==='completed'}"><button @click="activeTaskId=t.id"><span>{{ t.title }}</span><span class="badge" :class="t.status">{{ formatTaskStatus(t.status) }}</span></button></li></ul></div>
        <div class="side-actions"><button class="btn btn-primary btn-sm" @click="startNewResearch" style="width:100%">新研究</button></div>
      </aside>
      <section class="main">
        <div class="topbar"><span class="chip" :class="{live:loading}"><span class="dot"></span>{{ loading?'进行中':'已完成' }}</span><span class="topbar-skill" v-if="activeSkill">技能：{{ activeSkill }}</span><span class="topbar-meta">{{ progressLogs.length }} 条日志</span><button class="btn btn-secondary btn-sm" @click="showLogs=!showLogs">{{ showLogs?'收起':'展开' }}日志</button></div>
        <div v-if="showLogs && progressLogs.length" class="log-box"><p v-for="(l,i) in progressLogs" :key="i" class="log-line">{{ l }}</p></div>
	        <div v-if="memoryRecall.length" class="recall-banner">
        <span>🕮 语义记忆 — 你研究过相似话题：</span>
        <span v-for="(m,i) in memoryRecall" :key="i" class="recall-chip" :class="{expanded:expandedCard===i}" @click="expandedCard=expandedCard===i?null:i">
          {{ m.topic }}
          <em v-if="m.level==='high'">(高度相关)</em>
          <em v-else-if="m.level==='medium'">(中度相关)</em>
          <em v-else>(低度相关)</em>
          <div v-if="expandedCard===i" class="recall-preview">
            <div class="md" v-html="renderMd(m.preview||'暂无内容')"></div>
            <button class="btn btn-secondary btn-sm" @click.stop="expandedCard=null" style="margin-top:8px">收起</button>
          </div>
        </span>
      </div>
        <div class="card" v-if="currentTask"><h3>{{ currentTaskTitle }}</h3><p class="muted" v-if="currentTaskIntent && currentTaskIntent !== currentTaskTitle">{{ currentTaskIntent }}</p>
          <div v-if="currentTaskSources.length" class="section"><h4>来源</h4><ul class="src-list"><li v-for="(s,i) in currentTaskSources" :key="i"><a :href="s.url" target="_blank">{{ s.title||s.url }}</a><span v-if="s.snippet" class="snippet">{{ s.snippet.slice(0,200) }}</span></li></ul></div>
          <div class="section"><h4>任务总结</h4><div class="md" v-html="renderMd(currentTaskSummary||'暂无可用信息')"></div></div>
          <div class="section" v-if="currentTaskToolCalls.length"><h4>工具调用 ({{ currentTaskToolCalls.length }})</h4><div class="tool-entry" v-for="tc in currentTaskToolCalls" :key="tc.eventId"><div class="tool-head"><strong>{{ tc.agent }}</strong> <code>{{ tc.tool }}</code><span v-if="tc.noteId" class="note-id">笔记: {{ tc.noteId }}</span></div><pre class="tool-params">{{ JSON.stringify(tc.parameters, null, 2) }}</pre><pre class="tool-result" v-if="tc.result">{{ tc.result.slice(0, 500) }}</pre></div></div>
        </div>
        <div v-if="reportMarkdown" class="report-standalone"><div style="background:rgba(129,140,248,0.06);border:1px solid var(--color-border-active);border-radius:var(--radius-lg);padding:var(--space-6);"><h3 style="color:var(--color-accent-cyan);font-size:var(--font-size-xl);margin-top:0">最终研究报告 (全局)</h3><p class="muted" style="margin-bottom:var(--space-4)">以下报告综合所有子任务结论生成，独立于左侧任务清单</p><div class="md" v-html="renderMd(reportMarkdown)"></div></div></div>
        <div v-if="!currentTask && !reportMarkdown && todoTasks.length" class="empty">等待任务执行...</div>
      </section>
    </div>
  </main>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js/lib/core";
import { runResearchStream, type ResearchStreamEvent } from "./services/api";

const md = new MarkdownIt({ html:false, linkify:true, typographer:true, highlight(s:string,l:string){ if(l&&hljs.getLanguage(l)) try{return hljs.highlight(s,{language:l}).value}catch{} return ""; } });
function renderMd(t:string):string { return t?md.render(t):""; }

interface SourceItem { title:string; url:string; snippet:string; raw:string }
interface ToolCallLog { eventId:number; agent:string; tool:string; parameters:Record<string,unknown>; result:string; noteId:string|null; notePath:string|null; timestamp:number }
interface TodoTaskView { id:number; title:string; intent:string; query:string; status:string; summary:string; sourcesSummary:string; sourceItems:SourceItem[]; notices:string[]; noteId:string|null; notePath:string|null; toolCalls:ToolCallLog[] }

const form = reactive({ topic:"", searchApi:"" });
const loading = ref(false); const error = ref(""); const progressLogs = ref<string[]>([]);
const showLogs = ref(false); const isExpanded = ref(false);
const todoTasks = ref<TodoTaskView[]>([]); const activeTaskId = ref<number|null>(null);
const reportMarkdown = ref(""); const activeSkill = ref("");
const history = ref<{id:string;topic:string;created_at:number}[]>([]);
const historyDetail = ref<{id:string;topic:string;report_markdown:string}|null>(null);
const uploading = ref(false); const uploadMsg = ref(""); const kbStats = ref<number|null>(null);
const fileInput = ref<HTMLInputElement|null>(null);
const memoryRecall = ref<{topic:string;preview:string;level:string;session_id:string}[]>([]);
const expandedCard = ref<number|null>(null);
let currentController: AbortController|null = null;

const searchOptions = [{value:"duckduckgo",label:"DuckDuckGo"},{value:"hybrid",label:"Hybrid 混合"},{value:"tavily",label:"Tavily"},{value:"perplexity",label:"Perplexity"}];
const STATUS:Record<string,string>={pending:"待执行",in_progress:"进行中",completed:"已完成",skipped:"已跳过"};
function formatTaskStatus(s:string):string { return STATUS[s]??s; }
const totalTasks = computed(()=>todoTasks.value.length);
const completedTasks = computed(()=>todoTasks.value.filter(t=>t.status==="completed").length);
const currentTask = computed(()=>activeTaskId.value!==null?todoTasks.value.find(t=>t.id===activeTaskId.value)??null:todoTasks.value[0]??null);
const currentTaskSources = computed(()=>currentTask.value?.sourceItems??[]);
const currentTaskSummary = computed(()=>currentTask.value?.summary??"");
const currentTaskTitle = computed(()=>currentTask.value?.title??"");
const currentTaskIntent = computed(()=>currentTask.value?.intent??"");
const currentTaskToolCalls = computed(()=>currentTask.value?.toolCalls??[]);

function resetAll(){ todoTasks.value=[]; activeTaskId.value=null; reportMarkdown.value=""; progressLogs.value=[]; showLogs.value=false; activeSkill.value=""; memoryRecall.value=[]; }
function findTask(id:unknown):TodoTaskView|undefined { const n=typeof id==="number"?id:Number(id); return Number.isNaN(n)?undefined:todoTasks.value.find(t=>t.id===n); }

async function loadHistory(){ try{const r=await fetch("http://localhost:8000/memory/history?limit=10");if(r.ok)history.value=await r.json()}catch{} }
async function loadKBStats(){ try{const r=await fetch("http://localhost:8000/knowledge/stats");if(r.ok){const d=await r.json();kbStats.value=d.total_chunks||0}}catch{} }
async function loadHistoryDetail(id:string){ try{historyDetail.value=null;const r=await fetch("http://localhost:8000/memory/history/"+id);if(r.ok){const d=await r.json();historyDetail.value={id:d.id,topic:d.topic,report_markdown:d.report_markdown||''}}}catch{} }
onMounted(()=>{ loadHistory(); loadKBStats(); });

async function handleUpload(e:Event){ const f=(e.target as HTMLInputElement).files?.[0]; if(!f)return; uploading.value=true;uploadMsg.value=""; const fd=new FormData();fd.append("file",f); try{const r=await fetch("http://localhost:8000/knowledge/upload",{method:"POST",body:fd});const d=await r.json();uploadMsg.value=d.status==="ok"?d.filename+" OK: "+d.chunks+" chunks":"FAIL: "+d.message;loadKBStats()}catch(e:any){uploadMsg.value="FAIL: "+e.message} uploading.value=false; if(fileInput.value)fileInput.value.value="" }

const handleSubmit=async()=>{
  if(!form.topic.trim()){ error.value="请输入研究主题";return }
  if(currentController){ currentController.abort() }
  loading.value=true;error.value="";isExpanded.value=true;resetAll();
  const c=new AbortController();currentController=c;
  try{
    await runResearchStream({topic:form.topic.trim(),search_api:form.searchApi||undefined},(ev:ResearchStreamEvent)=>{
      const ep=ev as Record<string,unknown>;
      if(ev.type==="status"){ progressLogs.value.push(typeof ev.message==="string"?ev.message:"状态");return }
      if(ev.type==="skill"){ activeSkill.value=typeof ev.name==="string"?ev.name:"";progressLogs.value.push("匹配技能: "+activeSkill.value);return }
      if(ev.type==="todo_list"){ const items=Array.isArray(ev.tasks)?ev.tasks as Record<string,unknown>[]:[]; todoTasks.value=items.map((it,i)=>({id:Number(it.id)||i+1,title:String(it.title||"任务"),intent:String(it.intent||""),query:String(it.query||""),status:String(it.status||"pending"),summary:"",sourcesSummary:"",sourceItems:[],notices:[],noteId:null,notePath:null,toolCalls:[]})); if(todoTasks.value.length)activeTaskId.value=todoTasks.value[0].id; progressLogs.value.push("已生成 "+todoTasks.value.length+" 个任务");return }
      if(ev.type==="task_status"){ const task=findTask(ev.task_id);if(!task)return; task.status=String(ev.status||task.status); if(typeof ev.title==="string")task.title=ev.title; if(typeof ev.summary==="string"&&ev.summary.trim())task.summary=ev.summary.trim(); if(typeof ev.sources_summary==="string")task.sourcesSummary=ev.sources_summary.trim(); if(typeof ev.note_id==="string")task.noteId=ev.note_id;return }
      if(ev.type==="task_summary_chunk"){ const task=findTask(ev.task_id);if(task)task.summary+=typeof ev.content==="string"?ev.content:"";return }
if(ev.type==="task_summary_reset"){ const task=findTask(ev.task_id);if(task&&typeof ev.content==="string")task.summary=ev.content;return }
      if(ev.type==="sources"){ const task=findTask(ev.task_id);if(task){ const t=[ep.latest_sources,ep.sources_summary,ep.raw_context].find(v=>typeof v==="string") as string;if(t)task.sourcesSummary=t } return }
      if(ev.type==="tool_call"){ const task=findTask(ep.task_id); const entry:ToolCallLog={eventId:Number(ep.event_id)||Date.now(),agent:String(ep.agent||""),tool:String(ep.tool||""),parameters:(ep.parameters&&typeof ep.parameters==="object"?ep.parameters:{}) as Record<string,unknown>,result:String(ep.result||""),noteId:typeof ep.note_id==="string"?ep.note_id:null,notePath:typeof ep.note_path==="string"?ep.note_path:null,timestamp:Date.now()}; if(task){task.toolCalls.push(entry);if(entry.noteId)task.noteId=entry.noteId} progressLogs.value.push(entry.agent+" -> "+entry.tool);return }
      if(ev.type==="memory_recall"){ if(Array.isArray(ev.similar)&&ev.similar.length){ memoryRecall.value=ev.similar as {topic:string;preview:string;level:string;session_id:string}[]; progressLogs.value.push('语义记忆: 发现 '+ev.similar.length+' 个相似历史研究') } return }
      if(ev.type==="final_report"){ reportMarkdown.value=typeof ev.report==="string"?ev.report.trim():"";progressLogs.value.push("最终报告已生成");loadHistory();return }
      if(ev.type==="error"){ error.value=typeof ev.detail==="string"?ev.detail:"发生错误" }
    },{signal:c.signal});
    if(!reportMarkdown.value) reportMarkdown.value="报告生成失败，未获得有效内容";
  }catch(err:any){ if(err?.name!=="AbortError"){ error.value=err?.message||"请求失败" } }
  finally{ loading.value=false; if(currentController===c)currentController=null }
};
const cancelResearch=()=>{ if(currentController)currentController.abort() };
const goBack=()=>{ if(!loading.value)isExpanded.value=false };
const startNewResearch=()=>{ if(loading.value)cancelResearch(); resetAll(); isExpanded.value=false; form.topic=""; loadHistory() };
onBeforeUnmount(()=>{ if(currentController)currentController.abort() });
</script>
<style>
.app-shell { min-height:100vh; background:var(--color-bg-primary); color:var(--color-text-primary); font-family:var(--font-sans); }
.app-shell.expanded { display:flex; }
.hero { max-width:700px; margin:0 auto; padding:var(--space-10) var(--space-6); text-align:center; display:flex; flex-direction:column; align-items:center; gap:var(--space-6); }
.hero-icon { width:56px; height:56px; display:grid; place-items:center; border-radius:var(--radius-xl); background:linear-gradient(135deg,var(--color-accent-cyan),var(--color-accent-purple)); box-shadow:var(--shadow-glow); }
.hero-icon svg { width:28px; height:28px; fill:#fff; }
.hero h1 { font-size:var(--font-size-2xl); font-weight:700; margin:0; }
.hero-sub { color:var(--color-text-secondary); margin:0; font-size:var(--font-size-base); max-width:500px; }
.hero-form { width:100%; display:flex; flex-direction:column; gap:var(--space-4); }
.hero-input { width:100%; padding:var(--space-4); border-radius:var(--radius-lg); border:1px solid var(--color-border); background:var(--color-bg-card); color:var(--color-text-primary); font-size:var(--font-size-md); resize:none; outline:none; transition:border-color var(--transition-fast); }
.hero-input:focus { border-color:var(--color-border-active); box-shadow:0 0 0 3px rgba(56,189,248,0.15); }
.hero-row { display:flex; gap:var(--space-3); flex-wrap:wrap; }
.hero-select { flex:1; min-width:180px; padding:var(--space-3) var(--space-4); border-radius:var(--radius-md); border:1px solid var(--color-border); background:var(--color-bg-card); color:var(--color-text-primary); font-size:var(--font-size-sm); outline:none; }
.hero-select:focus { border-color:var(--color-border-active); }
.upload-zone { width:100%; padding:var(--space-4); border:1px dashed var(--color-border-hover); border-radius:var(--radius-lg); cursor:pointer; transition:all var(--transition-fast); }
.upload-zone:hover { border-color:var(--color-accent-cyan); background:rgba(56,189,248,0.04); }
.upload-hint { color:var(--color-text-muted); font-size:var(--font-size-sm); cursor:pointer; }
.upload-msg { margin:var(--space-2) 0 0; font-size:var(--font-size-xs); color:var(--color-accent-cyan); }
.kb-stats { margin:var(--space-1) 0 0; font-size:var(--font-size-xs); color:var(--color-success); }
.history-section { width:100%; text-align:left; }
.history-section h3 { font-size:var(--font-size-sm); color:var(--color-text-secondary); margin:0 0 var(--space-3); }
.history-section ul { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:var(--space-2); }
.history-section li { display:flex; justify-content:space-between; padding:var(--space-2) var(--space-3); background:var(--color-bg-card); border-radius:var(--radius-sm); font-size:var(--font-size-sm); cursor:pointer; }
.history-section li:hover { background:var(--color-bg-card-hover); }
.hist-topic { color:var(--color-text-primary); }
.hist-date { color:var(--color-text-muted); }
.history-detail { margin-top:var(--space-4); padding:var(--space-5); background:var(--color-bg-card); border:1px solid var(--color-border); border-radius:var(--radius-lg); }
.hist-detail-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--space-4); }
.hist-detail-head h4 { margin:0; font-size:var(--font-size-md); }
.error-msg { color:var(--color-error); font-size:var(--font-size-sm); margin:0; }
.spinner { width:18px; height:18px; fill:none; stroke:rgba(255,255,255,0.85); stroke-linecap:round; animation:spin 1s linear infinite; }
.workspace { display:flex; flex:1; height:100vh; overflow:hidden; }
.sidebar { width:260px; min-width:260px; background:var(--color-bg-secondary); border-right:1px solid var(--color-border); padding:var(--space-5); display:flex; flex-direction:column; gap:var(--space-5); overflow-y:auto; }
.side-head { display:flex; flex-direction:column; gap:var(--space-2); }
.side-head h2 { font-size:var(--font-size-lg); margin:0; }
.side-topic label { font-size:var(--font-size-xs); text-transform:uppercase; color:var(--color-text-muted); }
.side-topic p { font-weight:600; margin:var(--space-1) 0 0; font-size:var(--font-size-sm); word-break:break-word; }
.side-info { display:flex; flex-direction:column; gap:var(--space-3); }
.info-row { display:flex; align-items:center; gap:var(--space-2); font-size:var(--font-size-sm); }
.info-row label { color:var(--color-text-muted); font-size:var(--font-size-xs); }
.tag { padding:2px 8px; border-radius:var(--radius-full); font-size:var(--font-size-xs); }
.skill-tag { background:rgba(129,140,248,0.2); color:var(--color-accent-purple); }
.mini-bar { flex:1; height:4px; background:rgba(148,163,184,0.15); border-radius:2px; overflow:hidden; }
.mini-fill { height:100%; background:linear-gradient(90deg,var(--color-accent-cyan),var(--color-accent-purple)); border-radius:2px; transition:width 0.4s; }
.side-tasks h3 { font-size:var(--font-size-xs); color:var(--color-text-muted); margin:0 0 var(--space-2); }
.side-tasks ul { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:var(--space-1); }
.side-tasks li button { width:100%; display:flex; justify-content:space-between; align-items:center; padding:var(--space-2); background:transparent; border:1px solid transparent; border-radius:var(--radius-sm); color:var(--color-text-secondary); cursor:pointer; font-size:var(--font-size-xs); text-align:left; transition:all var(--transition-fast); }
.side-tasks li.active button { background:rgba(56,189,248,0.08); border-color:var(--color-border-active); color:var(--color-text-primary); }
.side-tasks li.done button { border-color:rgba(52,211,153,0.15); }
.badge { padding:1px 6px; border-radius:var(--radius-full); font-size:10px; }
.badge.pending { background:rgba(148,163,184,0.15); color:var(--color-text-muted); }
.badge.in_progress { background:rgba(129,140,248,0.2); color:var(--color-accent-purple); }
.badge.completed { background:rgba(52,211,153,0.15); color:var(--color-success); }
.side-actions { padding-top:var(--space-3); border-top:1px solid var(--color-border); }
.main { flex:1; overflow-y:auto; padding:var(--space-6); display:flex; flex-direction:column; gap:var(--space-5); }
.topbar { display:flex; align-items:center; gap:var(--space-3); flex-wrap:wrap; }
.chip { display:inline-flex; align-items:center; gap:6px; padding:var(--space-1) var(--space-3); border-radius:var(--radius-full); font-size:var(--font-size-sm); border:1px solid var(--color-border); color:var(--color-text-secondary); }
.chip .dot { width:6px; height:6px; border-radius:50%; background:var(--color-accent-cyan); }
.chip.live .dot { animation:glow-pulse 2s infinite; }
.topbar-skill { font-size:var(--font-size-sm); color:var(--color-accent-purple); font-weight:500; }
.topbar-meta { color:var(--color-text-muted); font-size:var(--font-size-sm); }
.log-box { max-height:160px; overflow-y:auto; background:var(--color-bg-card); border:1px solid var(--color-border); border-radius:var(--radius-md); padding:var(--space-3); }
.log-line { font-size:var(--font-size-xs); color:var(--color-text-muted); font-family:var(--font-mono); margin:0; }
.card { background:var(--color-bg-card); border:1px solid var(--color-border); border-radius:var(--radius-lg); padding:var(--space-6); }
.card h3 { margin:0 0 var(--space-2); font-size:var(--font-size-lg); }
.muted { color:var(--color-text-muted); margin:0; }
.section { margin-top:var(--space-5); }
.section h4 { font-size:var(--font-size-sm); font-weight:600; color:var(--color-text-secondary); margin:0 0 var(--space-3); }
.src-list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:var(--space-2); }
.src-list a { color:var(--color-accent-cyan); font-size:var(--font-size-sm); text-decoration:none; }
.snippet { display:block; font-size:var(--font-size-xs); color:var(--color-text-muted); }
.md { line-height:1.7; font-size:var(--font-size-base); color:var(--color-text-primary); }
.md :deep(h2) { color:var(--color-accent-cyan); margin:var(--space-5) 0 var(--space-2); font-size:var(--font-size-lg); }
.md :deep(h3) { margin:var(--space-4) 0 var(--space-2); font-size:var(--font-size-md); }
.md :deep(p) { margin:var(--space-2) 0; }
.md :deep(li) { margin:var(--space-1) 0; }
.md :deep(code) { font-family:var(--font-mono); background:rgba(56,189,248,0.1); padding:2px 6px; border-radius:4px; font-size:0.9em; }
.md :deep(pre) { background:var(--color-bg-input); border-radius:var(--radius-md); padding:var(--space-4); overflow-x:auto; }
.md :deep(pre code) { background:none; padding:0; }
.md :deep(a) { color:var(--color-accent-cyan); }
.report-standalone { border-top:2px solid var(--color-accent-cyan); margin-top:var(--space-8); padding-top:var(--space-6); }
.report-card { border-color:var(--color-border-active); }
.empty { display:flex; align-items:center; justify-content:center; height:200px; color:var(--color-text-muted); }
.recall-banner { display:flex; align-items:flex-start; gap:8px; flex-wrap:wrap; padding:10px 16px; background:rgba(56,189,248,0.08); border:1px solid var(--color-border-active); border-radius:var(--radius-md); font-size:var(--font-size-sm); color:var(--color-accent-cyan); }
.recall-chip { display:inline-block; padding:2px 10px; background:rgba(129,140,248,0.15); border-radius:var(--radius-full); font-size:var(--font-size-xs); color:var(--color-accent-purple); cursor:pointer; transition:all var(--transition-fast); position:relative; }
.recall-chip:hover { background:rgba(129,140,248,0.3); }
.recall-chip.expanded { border-radius:var(--radius-md); background:rgba(129,140,248,0.2); padding:8px 12px; width:100%; }
.recall-chip em { font-style:normal; color:var(--color-success); margin-left:4px; }
.recall-preview { margin-top:8px; padding:10px; background:rgba(0,0,0,0.2); border-radius:var(--radius-sm); font-size:var(--font-size-sm); color:var(--color-text-primary); max-height:300px; overflow-y:auto; }
.tool-entry { background:var(--color-bg-input); border:1px solid var(--color-border); border-radius:var(--radius-md); padding:var(--space-3); margin-top:var(--space-2); }
.tool-head { font-size:var(--font-size-xs); display:flex; gap:var(--space-2); align-items:center; flex-wrap:wrap; }
.tool-head code { font-family:var(--font-mono); color:var(--color-accent-cyan); }
.note-id { color:var(--color-success); font-size:10px; }
.tool-params, .tool-result { font-family:var(--font-mono); font-size:11px; background:rgba(0,0,0,0.2); padding:var(--space-2); border-radius:var(--radius-sm); margin-top:var(--space-1); overflow-x:auto; white-space:pre-wrap; max-height:150px; }
.btn-sm { padding:4px 10px; font-size:var(--font-size-xs); }
@media(max-width:768px){ .workspace{flex-direction:column} .sidebar{width:100%;min-width:100%;max-height:30vh} .main{height:70vh} .hero{padding:var(--space-6)} }
</style>