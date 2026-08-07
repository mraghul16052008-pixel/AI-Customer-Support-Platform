"use client";

import { FormEvent, useMemo, useState } from "react";

type Tab = "Dashboard" | "Conversations" | "Escalations" | "Analytics";
type ConversationStatus = "AI Resolved" | "Escalated" | "Human Resolved";

type Conversation = {
  id: string;
  name: string;
  issue: string;
  status: ConversationStatus;
  time: string;
  channel: string;
  order: string;
  intent: string;
  confidence: number;
  messages: { from: "customer" | "ai" | "agent"; text: string }[];
};

const conversations: Conversation[] = [
  {
    id: "CON-1048",
    name: "Arun",
    issue: "Order not delivered",
    status: "AI Resolved",
    time: "10:32 AM",
    channel: "ShopX app",
    order: "#SX-84192",
    intent: "Delivery status",
    confidence: 94,
    messages: [
      { from: "customer", text: "My order was due yesterday. Where is it?" },
      { from: "ai", text: "I found order #SX-84192. It was delayed at the Coimbatore hub and is now out for delivery today." },
      { from: "customer", text: "Okay, thank you." },
    ],
  },
  {
    id: "CON-1049",
    name: "Priya",
    issue: "Refund request",
    status: "Escalated",
    time: "11:05 AM",
    channel: "ShopX app",
    order: "#SX-84207",
    intent: "Refund",
    confidence: 52,
    messages: [
      { from: "customer", text: "I returned this order but my refund has not arrived." },
      { from: "ai", text: "I can see the return was received. I need a support agent to verify the payment status before I give you an answer." },
    ],
  },
  {
    id: "CON-1050",
    name: "Karthik",
    issue: "Wrong product received",
    status: "Human Resolved",
    time: "11:40 AM",
    channel: "ShopX app",
    order: "#SX-84231",
    intent: "Replacement",
    confidence: 61,
    messages: [
      { from: "customer", text: "The product in my package is not what I ordered." },
      { from: "ai", text: "I am escalating this because a replacement needs human verification." },
      { from: "agent", text: "I verified the order and created a free replacement. Pickup is scheduled for tomorrow." },
    ],
  },
  {
    id: "CON-1051",
    name: "Nisha",
    issue: "Change delivery address",
    status: "AI Resolved",
    time: "12:08 PM",
    channel: "ShopX app",
    order: "#SX-84246",
    intent: "Address update",
    confidence: 91,
    messages: [
      { from: "customer", text: "Can I change my delivery address before dispatch?" },
      { from: "ai", text: "Yes. Your order has not shipped yet, so I updated the delivery address you confirmed." },
    ],
  },
  {
    id: "CON-1052",
    name: "Rahul",
    issue: "Payment charged twice",
    status: "Escalated",
    time: "12:26 PM",
    channel: "ShopX app",
    order: "#SX-84258",
    intent: "Payment issue",
    confidence: 47,
    messages: [
      { from: "customer", text: "My card was charged two times for the same order." },
      { from: "ai", text: "This is a sensitive payment issue, so I am transferring it to a support agent for verification." },
    ],
  },
  {
    id: "CON-1053",
    name: "Meera",
    issue: "Cancel shipped order",
    status: "Escalated",
    time: "12:48 PM",
    channel: "ShopX app",
    order: "#SX-84273",
    intent: "Cancellation",
    confidence: 58,
    messages: [
      { from: "customer", text: "I need to cancel this order, but it already says shipped." },
      { from: "ai", text: "The order is already with the courier. I will ask a human agent to check the available cancellation options." },
    ],
  },
];

const metrics = [
  { label: "Total Conversations", value: "128", code: "TC", tone: "mint", note: "+18 today" },
  { label: "AI Resolved", value: "103", code: "AI", tone: "teal", note: "80.5% of total" },
  { label: "Escalated", value: "25", code: "ES", tone: "amber", note: "5 need attention" },
  { label: "AI Resolution Rate", value: "80.5%", code: "%", tone: "blue", note: "+3.2% this week" },
];

const escalationSeed = [
  { id: "ESC-205", conversationId: "CON-1049", name: "Priya", issue: "Refund request", reason: "Payment status requires verification", priority: "High", wait: "12 min" },
  { id: "ESC-206", conversationId: "CON-1052", name: "Rahul", issue: "Payment charged twice", reason: "Sensitive payment issue", priority: "Critical", wait: "7 min" },
  { id: "ESC-207", conversationId: "CON-1053", name: "Meera", issue: "Cancel shipped order", reason: "AI confidence below threshold", priority: "Medium", wait: "4 min" },
];

function StatusBadge({ status }: { status: ConversationStatus }) {
  return <span className={`status status-${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</span>;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("Dashboard");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"All" | ConversationStatus>("All");
  const [selectedConversation, setSelectedConversation] = useState(conversations[0].id);
  const [selectedEscalation, setSelectedEscalation] = useState(escalationSeed[0].id);
  const [escalationStates, setEscalationStates] = useState<Record<string, "Waiting" | "In progress" | "Resolved">>({});
  const [draft, setDraft] = useState("");
  const [activityMessage, setActivityMessage] = useState("");

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    return conversations.filter((item) => {
      const matchesSearch = !query || [item.name, item.issue, item.id, item.order].some((value) => value.toLowerCase().includes(query));
      const matchesStatus = statusFilter === "All" || item.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [search, statusFilter]);

  const selected = conversations.find((item) => item.id === selectedConversation) ?? conversations[0];
  const escalation = escalationSeed.find((item) => item.id === selectedEscalation) ?? escalationSeed[0];
  const escalationConversation = conversations.find((item) => item.id === escalation.conversationId)!;
  const escalationState = escalationStates[escalation.id] ?? "Waiting";

  function navigate(tab: Tab) {
    setActiveTab(tab);
    setActivityMessage("");
  }

  function sendReply(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    setActivityMessage(`Reply sent to ${escalation.name} (demo).`);
    setDraft("");
  }

  return (
    <div className="console-shell">
      <aside className="sidebar">
        <div>
          <div className="brand-mark" aria-hidden="true">S</div>
          <div className="brand-copy">
            <strong>SupportAI</strong>
            <span>Business Console</span>
          </div>
        </div>

        <nav aria-label="Main navigation">
          {(["Dashboard", "Conversations", "Escalations", "Analytics"] as Tab[]).map((tab) => (
            <button key={tab} className={activeTab === tab ? "nav-item active" : "nav-item"} onClick={() => navigate(tab)} aria-current={activeTab === tab ? "page" : undefined}>
              <span className="nav-dot" aria-hidden="true" />
              {tab}
              {tab === "Escalations" && <span className="nav-count">3</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <span className="connection-dot" />
          <div><strong>Demo workspace</strong><small>Backend ready to connect</small></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">SUPPORT OPERATIONS</p>
            <h1>{activeTab === "Dashboard" ? "Support Dashboard" : activeTab}</h1>
            <p className="subtitle">
              {activeTab === "Dashboard" && "Monitor AI conversations and customer escalations."}
              {activeTab === "Conversations" && "Review every customer interaction handled by your support AI."}
              {activeTab === "Escalations" && "Take over sensitive or low-confidence conversations."}
              {activeTab === "Analytics" && "Understand how your AI support operation is performing."}
            </p>
          </div>
          <div className="demo-pill"><span /> Demo data</div>
        </header>

        {activeTab === "Dashboard" && (
          <section className="page-section" aria-label="Dashboard overview">
            <div className="metric-grid">
              {metrics.map((metric) => (
                <article className="metric-card" key={metric.label}>
                  <div className={`metric-icon ${metric.tone}`}>{metric.code}</div>
                  <div><span className="metric-label">{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>
                </article>
              ))}
            </div>

            <section className="panel recent-panel">
              <div className="panel-head">
                <div><h2>Recent Conversations</h2><p>Latest customer support activity</p></div>
                <button className="secondary-button" onClick={() => navigate("Conversations")}>View all</button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Customer</th><th>Issue</th><th>Status</th><th>Time</th></tr></thead>
                  <tbody>
                    {conversations.slice(0, 4).map((item) => (
                      <tr key={item.id} onClick={() => { setSelectedConversation(item.id); navigate("Conversations"); }} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") { setSelectedConversation(item.id); navigate("Conversations"); } }}>
                        <td><div className="customer-cell"><span className="avatar">{item.name[0]}</span><div><strong>{item.name}</strong><small>{item.id}</small></div></div></td>
                        <td>{item.issue}</td><td><StatusBadge status={item.status} /></td><td>{item.time}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </section>
        )}

        {activeTab === "Conversations" && (
          <section className="page-section conversations-layout">
            <div className="panel conversation-list">
              <div className="filter-row">
                <label className="search-field"><span>Search</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Customer, order or issue" /></label>
                <label className="filter-field"><span>Status</span><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "All" | ConversationStatus)}><option>All</option><option>AI Resolved</option><option>Escalated</option><option>Human Resolved</option></select></label>
              </div>
              <div className="result-count">{filteredConversations.length} conversations</div>
              <div className="conversation-items">
                {filteredConversations.map((item) => (
                  <button key={item.id} className={selected.id === item.id ? "conversation-item selected" : "conversation-item"} onClick={() => setSelectedConversation(item.id)}>
                    <span className="avatar">{item.name[0]}</span>
                    <span className="conversation-summary"><strong>{item.name}<small>{item.time}</small></strong><span>{item.issue}</span><em>{item.id} · {item.channel}</em></span>
                    <StatusBadge status={item.status} />
                  </button>
                ))}
                {filteredConversations.length === 0 && <div className="empty-state">No conversations match your filters.</div>}
              </div>
            </div>

            <aside className="panel detail-panel" aria-label="Selected conversation">
              <div className="detail-head"><div><p>{selected.id}</p><h2>{selected.name}</h2></div><StatusBadge status={selected.status} /></div>
              <div className="context-grid">
                <div><span>Order</span><strong>{selected.order}</strong></div><div><span>Intent</span><strong>{selected.intent}</strong></div><div><span>AI confidence</span><strong>{selected.confidence}%</strong></div><div><span>Source</span><strong>{selected.channel}</strong></div>
              </div>
              <div className="chat-thread">
                {selected.messages.map((message, index) => (
                  <div key={index} className={`chat-message ${message.from}`}><span>{message.from === "customer" ? selected.name : message.from === "ai" ? "SupportAI" : "Human agent"}</span><p>{message.text}</p></div>
                ))}
              </div>
              {selected.status === "Escalated" && <button className="primary-button full" onClick={() => { const match = escalationSeed.find((item) => item.conversationId === selected.id); if (match) setSelectedEscalation(match.id); navigate("Escalations"); }}>Open escalation</button>}
            </aside>
          </section>
        )}

        {activeTab === "Escalations" && (
          <section className="page-section escalation-layout">
            <div className="panel escalation-queue">
              <div className="panel-head"><div><h2>Escalation Queue</h2><p>3 cases require human review</p></div></div>
              <div className="queue-items">
                {escalationSeed.map((item) => {
                  const state = escalationStates[item.id] ?? "Waiting";
                  return <button key={item.id} className={selectedEscalation === item.id ? "queue-card selected" : "queue-card"} onClick={() => { setSelectedEscalation(item.id); setActivityMessage(""); }}>
                    <div className="queue-top"><strong>{item.name}</strong><span className={`priority priority-${item.priority.toLowerCase()}`}>{item.priority}</span></div>
                    <h3>{item.issue}</h3><p>{item.reason}</p>
                    <div className="queue-meta"><span>{item.id}</span><span>{state}</span><span>{item.wait} wait</span></div>
                  </button>;
                })}
              </div>
            </div>

            <div className="panel takeover-panel">
              <div className="detail-head"><div><p>{escalation.id} · {escalationConversation.order}</p><h2>{escalation.name}: {escalation.issue}</h2></div><span className={`case-state state-${escalationState.toLowerCase().replace(" ", "-")}`}>{escalationState}</span></div>
              <div className="escalation-reason"><span>Why AI escalated</span><p>{escalation.reason}. Confidence score: {escalationConversation.confidence}%.</p></div>
              <div className="chat-thread compact">
                {escalationConversation.messages.map((message, index) => <div key={index} className={`chat-message ${message.from}`}><span>{message.from === "customer" ? escalation.name : message.from === "ai" ? "SupportAI" : "Human agent"}</span><p>{message.text}</p></div>)}
              </div>
              {escalationState === "Waiting" ? (
                <button className="primary-button full" onClick={() => { setEscalationStates((prev) => ({ ...prev, [escalation.id]: "In progress" })); setActivityMessage(`You took over ${escalation.id} (demo).`); }}>Take over case</button>
              ) : escalationState === "In progress" ? (
                <form className="reply-box" onSubmit={sendReply}>
                  <label htmlFor="agent-reply">Human agent reply</label>
                  <textarea id="agent-reply" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={`Reply to ${escalation.name}…`} rows={3} />
                  <div><button type="submit" className="secondary-button">Send reply</button><button type="button" className="primary-button" onClick={() => { setEscalationStates((prev) => ({ ...prev, [escalation.id]: "Resolved" })); setActivityMessage(`${escalation.id} marked resolved (demo).`); }}>Resolve case</button></div>
                </form>
              ) : <div className="resolved-callout">✓ Case resolved by human support</div>}
              {activityMessage && <div className="activity-message" role="status">{activityMessage}</div>}
            </div>
          </section>
        )}

        {activeTab === "Analytics" && (
          <section className="page-section analytics-page">
            <div className="analytics-summary">
              <article><span>AI resolution</span><strong>80.5%</strong><small>↑ 3.2% vs last week</small></article>
              <article><span>Avg. response time</span><strong>1.8s</strong><small>↓ 0.4s vs last week</small></article>
              <article><span>Human takeover</span><strong>19.5%</strong><small>25 of 128 conversations</small></article>
            </div>
            <div className="analytics-grid">
              <section className="panel chart-card"><div className="panel-head"><div><h2>Conversations this week</h2><p>AI resolved vs escalated</p></div></div><div className="bar-chart" aria-label="Weekly conversation volume chart">
                {[{d:"Mon",a:70,e:20},{d:"Tue",a:86,e:25},{d:"Wed",a:62,e:18},{d:"Thu",a:95,e:30},{d:"Fri",a:78,e:22},{d:"Sat",a:52,e:15},{d:"Sun",a:66,e:18}].map((bar) => <div className="bar-column" key={bar.d}><div className="bars"><span className="bar ai-bar" style={{height:`${bar.a}%`}}/><span className="bar esc-bar" style={{height:`${bar.e}%`}}/></div><small>{bar.d}</small></div>)}
              </div><div className="chart-legend"><span><i className="legend-ai"/> AI resolved</span><span><i className="legend-esc"/> Escalated</span></div></section>
              <section className="panel intent-card"><div className="panel-head"><div><h2>Top customer intents</h2><p>Most common reasons customers contact support</p></div></div><div className="intent-list">
                {[{name:"Delivery status",value:34},{name:"Refund & returns",value:26},{name:"Order changes",value:18},{name:"Payment issues",value:13},{name:"Product questions",value:9}].map((intent) => <div className="intent-row" key={intent.name}><div><span>{intent.name}</span><strong>{intent.value}%</strong></div><div className="progress-track"><span style={{width:`${intent.value * 2.6}%`}}/></div></div>)}
              </div></section>
            </div>
            <div className="insight-card"><span>AI insight</span><strong>Delivery questions are the biggest automation opportunity.</strong><p>They make up 34% of support volume and are resolved by AI with high confidence in this demo dataset.</p></div>
          </section>
        )}
      </main>
    </div>
  );
}
