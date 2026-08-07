"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type View = "home" | "products" | "checkout" | "confirmed" | "orders" | "support";
type Product = { icon: string; name: string; category: string; price: string; tone: string };
type Message = { from: "ai" | "user"; text: string; meta?: string };
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

const products: Product[] = [
  { icon: "🎧", name: "Orbit Pro Headphones", category: "Audio", price: "₹4,999", tone: "mint" },
  { icon: "⌚", name: "Pulse Smartwatch S2", category: "Wearables", price: "₹6,499", tone: "blue" },
  { icon: "⌨️", name: "KeyLite Mechanical", category: "Accessories", price: "₹3,299", tone: "peach" },
];

const initialMessages: Message[] = [
  { from: "ai", text: "Hi! I’m ShopX AI Support. Ask me about a saved order, delivery, returns, or refunds." },
];

async function supportApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/support/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const payload = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(payload.detail || "The support service could not complete the request.");
  return payload as T;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
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
  const [orderError, setOrderError] = useState("");
  const [supportError, setSupportError] = useState("");

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

  useEffect(() => { void refreshOrders(); }, [refreshOrders]);

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
      setMessages((current) => [...current, { from: "ai", text: result.reply, meta }]);
    } catch (error) {
      setSupportError(error instanceof Error ? error.message : "Support chat is unavailable.");
    } finally {
      setSendingMessage(false);
    }
  }

  function sendMessage(event: FormEvent) { event.preventDefault(); void answerIssue(draft); }
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

    {view === "support" && <section className="support-flow"><div className="support-info"><span className="eyebrow">STEP 4 • CUSTOMER ASKS FOR HELP</span><h1>AI Order Support</h1><p>The customer enters support from a saved order. The backend receives the order context automatically.</p>{supportOrder ? <div className="linked-order"><div className="order-icon small">🎧</div><div><small>LINKED ORDER</small><strong>#{supportOrder.external_order_id} • {supportOrder.product_name}</strong><span>Status: {supportOrder.status}</span></div><b>PostgreSQL order context sent to AI ✓</b></div> : <button className="primary" disabled={!orders.length} onClick={() => openOrderSupport(orders[0] ?? null)}>{orders.length ? "Load latest saved order" : "Place an order first"}</button>}<div className="demo-hint"><strong>Try both outcomes:</strong><span>“Where is my order?” → order-status response</span><span>“My item arrived damaged” → human escalation</span></div></div><div className="support-chat-card"><div className="chat-head inline"><div className="ai-logo">✦</div><div><strong>ShopX AI Support</strong><span><i></i> Connected to FastAPI + Gemini</span></div></div><div className="messages large">{messages.map((message, index) => <div key={index} className={`message ${message.from}`}>{message.text}{message.meta && <small className="message-meta">✓ {message.meta}</small>}</div>)}</div><div className="quick"><button disabled={sendingMessage} onClick={() => void answerIssue("Where is my order?")}>Where is my order?</button><button disabled={sendingMessage} onClick={() => void answerIssue("My item arrived damaged")}>Item arrived damaged</button><button disabled={sendingMessage} onClick={() => void answerIssue("Can I return this order?")}>Return question</button></div><form className="support-form" onSubmit={sendMessage}><input value={draft} disabled={sendingMessage} onChange={(event) => setDraft(event.target.value)} placeholder="Describe your problem…" aria-label="Chat message"/><button type="submit" disabled={sendingMessage}>{sendingMessage ? "…" : "Send"}</button></form>{supportError && <small className="chat-note" role="alert">{supportError}</small>}<small className="chat-note">Replies and escalation IDs come from the live support backend.</small></div></section>}

    {view !== "support" && <button className="chat-fab" onClick={() => openOrderSupport()} aria-label="Open AI support"><span>✦</span><div><strong>Need help?</strong><small>Ask ShopX AI</small></div></button>}
  </main>;
}
