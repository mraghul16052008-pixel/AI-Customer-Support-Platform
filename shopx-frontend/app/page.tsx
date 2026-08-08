"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type View = "home" | "products" | "checkout" | "confirmed" | "orders" | "support";
type Product = { icon: string; name: string; category: string; price: string; tone: string };
type Message = {
  from: "ai" | "user";
  text: string;
  meta?: string;
  attachment?: { name: string; size: number; previewUrl: string };
};
type Order = {
  id: number;
  customer_id: number;
  external_order_id: string;
  product_name: string;
  amount: string;
  status: string;
  created_at: string;
};
type ChatResult = {
  conversation_id: number;
  reply: string;
  intent: string;
  confidence: number;
  should_escalate: boolean;
  escalation_id: number | null;
};

type EvidenceResult = {
  conversation_id: number;
  reply: string;
  evidence_count: number;
  confidence: number;
  recommended_resolution: string;
  escalation_id: number;
};

const products: Product[] = [
  { icon: "🎧", name: "Orbit Pro Headphones", category: "Audio", price: "₹4,999", tone: "mint" },
  { icon: "⌚", name: "Pulse Smartwatch S2", category: "Wearables", price: "₹6,499", tone: "blue" },
  { icon: "⌨️", name: "KeyLite Mechanical", category: "Accessories", price: "₹3,299", tone: "peach" },
];

const initialMessages: Message[] = [
  { from: "ai", text: "Hi! I’m ShopX AI Support. Ask me about a saved order, delivery, returns, or refunds." },
];

async function supportApi<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`/api/support/${path}`, {
    ...init,
    headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...init?.headers },
  });
  const payload = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(payload.detail || "The support service could not complete the request.");
  return payload as T;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatFileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Home() {
  const [view, setView] = useState<View>("home");
  const [selected, setSelected] = useState<Product>(products[0]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [createdOrder, setCreatedOrder] = useState<Order | null>(null);
  const [supportOrder, setSupportOrder] = useState<Order | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [placingOrder, setPlacingOrder] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [uploadingEvidence, setUploadingEvidence] = useState(false);
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [escalationId, setEscalationId] = useState<number | null>(null);
  const [orderError, setOrderError] = useState("");
  const [supportError, setSupportError] = useState("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const refreshOrders = useCallback(async () => {
    setOrdersLoading(true);
    setOrderError("");
    try {
      const savedOrders = await supportApi<Order[]>("customers/1/orders");
      setOrders([...savedOrders].reverse());
    } catch (error) {
      setOrderError(error instanceof Error ? error.message : "Orders are unavailable.");
    } finally {
      setOrdersLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    supportApi<Order[]>("customers/1/orders")
      .then((savedOrders) => {
        if (!cancelled) setOrders([...savedOrders].reverse());
      })
      .catch((error: unknown) => {
        if (!cancelled) setOrderError(error instanceof Error ? error.message : "Orders are unavailable.");
      })
      .finally(() => {
        if (!cancelled) setOrdersLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (view === "support") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, sendingMessage, uploadingEvidence, view]);

  function navigate(next: View) {
    setView(next);
    if (next === "orders") void refreshOrders();
  }

  function buy(product: Product) { setSelected(product); setView("checkout"); }

  async function placeOrder() {
    setPlacingOrder(true);
    setOrderError("");
    try {
      const order = await supportApi<Order>("orders", {
        method: "POST",
        body: JSON.stringify({
          customer_id: 1,
          external_order_id: `SHOPX-${Date.now()}-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
          product_name: selected.name,
          amount: selected.price.replace(/[^\d.]/g, ""),
          status: "processing",
        }),
      });
      setCreatedOrder(order);
      setOrders((current) => [order, ...current.filter((item) => item.id !== order.id)]);
      setSupportOrder(order);
      setConversationId(null);
      setView("confirmed");
    } catch (error) {
      setOrderError(error instanceof Error ? error.message : "The order could not be placed.");
    } finally {
      setPlacingOrder(false);
    }
  }

  function openOrderSupport(order: Order | null = createdOrder ?? orders[0] ?? null) {
    if (order?.id !== supportOrder?.id) {
      setConversationId(null);
      setMessages(initialMessages);
      setEvidenceCount(0);
      setEscalationId(null);
    }
    setSupportOrder(order);
    setSupportError("");
    setView("support");
  }

  async function answerIssue(text: string) {
    if (!text.trim() || sendingMessage) return;
    const customerText = text.trim();
    setMessages((current) => [...current, { from: "user", text: customerText }]);
    setDraft("");
    setSupportError("");
    setSendingMessage(true);
    try {
      const result = await supportApi<ChatResult>("chat", {
        method: "POST",
        body: JSON.stringify({
          customer_id: 1,
          order_id: supportOrder?.id ?? null,
          conversation_id: conversationId,
          message: customerText,
        }),
      });
      setConversationId(result.conversation_id);
      const meta = result.should_escalate
        ? `Escalated to human${result.escalation_id ? ` • Ticket #${result.escalation_id}` : ""}`
        : `${result.intent.replaceAll("_", " ")} • ${Math.round(result.confidence * 100)}% confidence`;
      if (result.escalation_id) setEscalationId(result.escalation_id);
      setMessages((current) => [...current, { from: "ai", text: result.reply, meta }]);
    } catch (error) {
      setSupportError(error instanceof Error ? error.message : "Support chat is unavailable.");
    } finally {
      setSendingMessage(false);
    }
  }

  function sendMessage(event: FormEvent) { event.preventDefault(); void answerIssue(draft); }

  async function uploadEvidence(file: File) {
    if (!conversationId || !supportOrder || uploadingEvidence) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 4 * 1024 * 1024) {
      setSupportError("Choose a valid JPEG, PNG, or WebP image up to 4 MB.");
      return;
    }
    setUploadingEvidence(true);
    setSupportError("");
    const form = new FormData();
    form.append("customer_id", "1");
    form.append("order_id", String(supportOrder.id));
    form.append("conversation_id", String(conversationId));
    form.append("file", file);
    const previewUrl = URL.createObjectURL(file);
    setMessages((current) => [
      ...current,
      {
        from: "user",
        text: "I’ve attached a photo for the support investigation.",
        meta: `Customer evidence • ${formatFileSize(file.size)}`,
        attachment: { name: file.name, size: file.size, previewUrl },
      },
    ]);
    try {
      const result = await supportApi<EvidenceResult>("chat/evidence", { method: "POST", body: form });
      setEvidenceCount(result.evidence_count);
      setEscalationId(result.escalation_id);
      setMessages((current) => [...current, {
        from: "ai",
        text: result.reply,
        meta: `Evidence reviewed • ${Math.round(result.confidence * 100)}% confidence • Recommendation: ${result.recommended_resolution}`,
      }]);
    } catch (error) {
      setSupportError(error instanceof Error ? error.message : "Evidence upload failed.");
    } finally {
      setUploadingEvidence(false);
    }
  }

  function startNewSupportChat() {
    messages.forEach((message) => {
      if (message.attachment?.previewUrl) URL.revokeObjectURL(message.attachment.previewUrl);
    });
    setConversationId(null);
    setMessages(initialMessages);
    setEvidenceCount(0);
    setEscalationId(null);
    setSupportError("");
    setDraft("");
  }
  const navView = view === "checkout" || view === "confirmed" ? "products" : view;

  return <main>
    <header className="topbar">
      <button className="brand" onClick={() => navigate("home")} aria-label="ShopX home"><span className="brand-mark">S</span><span>ShopX</span></button>
      <nav aria-label="Main navigation">{(["home", "products", "orders", "support"] as View[]).map((item) => <button key={item} className={navView === item ? "nav-active" : ""} onClick={() => item === "support" ? openOrderSupport() : navigate(item)}>{item === "support" ? "Help & Support" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
      <div className="header-actions"><button aria-label="Cart">Bag <span>{orders.length}</span></button><div className="avatar">SR</div></div>
    </header>

    {view === "home" && <section className="hero">
      <div className="hero-copy"><span className="eyebrow">SHOP • ORDER • GET INSTANT SUPPORT</span><h1>Shop normally.<br/><em>Get help instantly.</em></h1><p>ShopX is our demo store showing how an existing shopping app can integrate our AI customer-support platform.</p><div className="hero-buttons"><button className="primary" onClick={() => navigate("products")}>Start demo purchase →</button><button className="secondary" onClick={() => navigate("orders")}>View saved orders</button></div><div className="trust"><span>1. Place order</span><span>2. Face a problem</span><span>3. Ask AI support</span></div></div>
      <div className="hero-art"><div className="headphone">🎧</div><div className="floating-card"><small>DEMO PRODUCT</small><strong>Orbit Pro</strong><span>Use this product to try the complete support flow.</span><b>₹4,999</b></div></div>
    </section>}

    {view === "products" && <section className="section page"><span className="eyebrow">STEP 1 • CUSTOMER SHOPS</span><h1>Choose a product</h1><p className="page-lead">Purchase any item and continue through the live order flow.</p><div className="product-grid">{products.map((product) => <article className="product" key={product.name}><div className={`product-image ${product.tone}`}>{product.icon}<span>★ 4.8</span></div><small>{product.category}</small><h3>{product.name}</h3><div><strong>{product.price}</strong><button className="buy-button" onClick={() => buy(product)} aria-label={`Buy ${product.name}`}>Buy now</button></div></article>)}</div></section>}

    {view === "checkout" && <section className="flow-page"><div className="flow-steps"><span className="done">1 Product</span><i>→</i><span className="active">2 Checkout</span><i>→</i><span>3 Order</span><i>→</i><span>4 Support</span></div><div className="checkout-grid"><div><span className="eyebrow">STEP 2 • PLACE DEMO ORDER</span><h1>Checkout</h1><div className="address-card"><small>DELIVER TO</small><strong>Sree Ram</strong><p>Singanallur, Coimbatore, Tamil Nadu 641005</p><button>Change</button></div><div className="payment-card"><small>PAYMENT METHOD</small><strong>Demo payment</strong><p>No real payment will be processed.</p><span>✓ Prototype mode</span></div>{orderError && <div className="problem-note" role="alert"><b>Order unavailable</b><span>{orderError}</span></div>}</div><aside className="summary-card"><h3>Order summary</h3><div className={`summary-product ${selected.tone}`}><span>{selected.icon}</span><div><strong>{selected.name}</strong><small>Qty 1</small></div></div><div className="summary-row"><span>Product</span><b>{selected.price}</b></div><div className="summary-row"><span>Delivery</span><b>FREE</b></div><div className="summary-total"><span>Total</span><strong>{selected.price}</strong></div><button className="primary full" disabled={placingOrder} onClick={() => void placeOrder()}>{placingOrder ? "Saving order…" : "Place demo order"}</button><small className="safe-note">This is a prototype. No payment is taken.</small></aside></div></section>}

    {view === "confirmed" && createdOrder && <section className="confirmed"><div className="success-mark">✓</div><span className="eyebrow">ORDER SAVED</span><h1>Order confirmed!</h1><p>Order <strong>#{createdOrder.external_order_id}</strong> is stored in PostgreSQL.</p><div className="mini-order"><span>{selected.icon}</span><div><strong>{createdOrder.product_name}</strong><small>Status: {createdOrder.status}</small></div></div><button className="primary" onClick={() => navigate("orders")}>View this order →</button></section>}

    {view === "orders" && <section className="section page"><span className="eyebrow">STEP 3 • CUSTOMER SELECTS AN ORDER</span><h1>My Orders</h1><p className="page-lead">These orders are loaded from the ShopX PostgreSQL account.</p>{ordersLoading && <div className="empty-state">Loading saved orders…</div>}{orderError && <div className="problem-note" role="alert"><b>Orders unavailable</b><span>{orderError}</span></div>}{!ordersLoading && !orderError && orders.length === 0 && <div className="empty-state">No saved orders yet. Place an order to start the demo.</div>}<div className="saved-orders">{orders.map((order) => <article className="order-card problem" key={order.id}><div className="order-icon">🎧</div><div><small>ORDER #{order.external_order_id}</small><h3>{order.product_name}</h3><p>Saved {formatDate(order.created_at)} • ₹{order.amount}</p><div className="track"><span className="passed">✓ Order saved</span><span className="warning">{order.status}</span></div><div className="problem-note"><b>Live backend status</b><span>{order.status}</span></div></div><div className="order-status"><span className="late">● {order.status}</span><button className="support-cta" onClick={() => openOrderSupport(order)}>Get help with this order →</button></div></article>)}</div></section>}

    {view === "support" && <section className="support-flow">
      <aside className="support-info">
        <span className="eyebrow">CUSTOMER SUPPORT • LIVE CASE</span>
        <h1>Help that knows your order.</h1>
        <p>ShopX sends the selected order to the support platform, so the AI can investigate without asking you to repeat information we already know.</p>

        {supportOrder ? <div className="linked-order enhanced">
          <div className="order-icon small">🎧</div>
          <div><small>LINKED ORDER</small><strong>#{supportOrder.external_order_id}</strong><span>{supportOrder.product_name}</span></div>
          <span className="order-state">{supportOrder.status}</span>
          <b>✓ Verified order context from PostgreSQL</b>
        </div> : <button className="primary" disabled={!orders.length} onClick={() => openOrderSupport(orders[0] ?? null)}>{orders.length ? "Load latest saved order" : "Place an order first"}</button>}

        <div className="case-progress" aria-label="Support case progress">
          <div className={supportOrder ? "done" : "active"}><span>1</span><div><strong>Order linked</strong><small>{supportOrder ? "Verified customer order loaded" : "Select an order to begin"}</small></div></div>
          <div className={conversationId ? "done" : supportOrder ? "active" : ""}><span>2</span><div><strong>AI investigation</strong><small>{conversationId ? "Conversation context is being remembered" : "Describe what went wrong"}</small></div></div>
          <div className={evidenceCount ? "done" : conversationId ? "active" : ""}><span>3</span><div><strong>Evidence</strong><small>{evidenceCount ? `${evidenceCount} photo${evidenceCount === 1 ? "" : "s"} reviewed` : "Attach a photo if the AI requests it"}</small></div></div>
          <div className={escalationId ? "escalated" : ""}><span>4</span><div><strong>Human decision</strong><small>{escalationId ? `Ticket #${escalationId} is ready for an agent` : "Used for sensitive or uncertain cases"}</small></div></div>
        </div>

        <div className="privacy-note"><span>🔒</span><div><strong>Your evidence stays with this support case</strong><small>Photos are treated as customer-provided evidence. Refund and replacement decisions remain with a human agent.</small></div></div>
      </aside>

      <div className="support-chat-card upgraded">
        <div className="chat-head inline upgraded-head">
          <div className="ai-logo">✦</div>
          <div><strong>ShopX AI Support</strong><span><i></i> Live • FastAPI + Gemini</span></div>
          <button className="new-chat-button" type="button" onClick={startNewSupportChat} disabled={sendingMessage || uploadingEvidence}>New chat</button>
        </div>

        {escalationId && <div className="escalation-banner"><span>👤</span><div><strong>Human review requested</strong><small>Ticket #{escalationId} • The full conversation and order context are attached.</small></div></div>}

        <div className="messages large upgraded-messages" role="log" aria-live="polite">
          {messages.map((message, index) => <div key={index} className={`message-wrap ${message.from}`}>
            <span className="message-sender">{message.from === "ai" ? "✦ AI Support" : "You"}</span>
            <div className={`message ${message.from}`}>
              {message.attachment && <div className="evidence-preview">
                <div className="evidence-thumb" style={{ backgroundImage: `url(${message.attachment.previewUrl})` }} role="img" aria-label={`Preview of ${message.attachment.name}`} />
                <div><strong>{message.attachment.name}</strong><small>{formatFileSize(message.attachment.size)} • Customer photo</small></div>
              </div>}
              <span>{message.text}</span>
              {message.meta && <small className="message-meta">✓ {message.meta}</small>}
            </div>
          </div>)}
          {(sendingMessage || uploadingEvidence) && <div className="message-wrap ai pending"><span className="message-sender">✦ AI Support</span><div className="message ai typing"><i></i><i></i><i></i><span>{uploadingEvidence ? "Reviewing your evidence…" : "Checking your case…"}</span></div></div>}
          <div ref={messagesEndRef} />
        </div>

        {supportError && <div className="support-error" role="alert"><span>!</span>{supportError}</div>}

        <div className="composer-area">
          <div className="quick upgraded-quick">
            <button disabled={sendingMessage} onClick={() => void answerIssue("Where is my order?")}>Track my order</button>
            <button disabled={sendingMessage} onClick={() => void answerIssue("My item arrived damaged")}>Report damage</button>
            <button disabled={sendingMessage} onClick={() => void answerIssue("Can I return this order?")}>Return or refund</button>
          </div>
          <form className="support-form upgraded-form" onSubmit={sendMessage}>
            <label className={`attach-button ${!conversationId ? "disabled" : ""}`} title={conversationId ? "Attach JPEG, PNG or WebP evidence" : "Send your first message before attaching evidence"}>
              <span>＋</span><b>{uploadingEvidence ? "Uploading" : "Photo"}</b>
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={!conversationId || uploadingEvidence} onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadEvidence(file); event.target.value = ""; }}/>
            </label>
            <input value={draft} disabled={sendingMessage} onChange={(event) => setDraft(event.target.value)} placeholder={conversationId ? "Reply to AI Support…" : "Tell us what happened…"} aria-label="Chat message"/>
            <button className="send-button" type="submit" disabled={sendingMessage || !draft.trim()} aria-label="Send message">Send <span>↑</span></button>
          </form>
          <div className="composer-help"><span>{conversationId ? `Case conversation #${conversationId}` : "Send a message to start a secure case"}</span><span>Photos: JPG, PNG or WebP • max 4 MB</span></div>
        </div>
      </div>
    </section>}

    {view !== "support" && <button className="chat-fab" onClick={() => openOrderSupport()} aria-label="Open AI support"><span>✦</span><div><strong>Need help?</strong><small>Ask ShopX AI</small></div></button>}
  </main>;
}
