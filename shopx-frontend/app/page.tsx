"use client";

import { FormEvent, useState } from "react";

type View = "home" | "products" | "checkout" | "confirmed" | "orders" | "support";
type Product = { icon: string; name: string; category: string; price: string; tone: string };
type Message = { from: "ai" | "user"; text: string; meta?: string };

const products: Product[] = [
  { icon: "🎧", name: "Orbit Pro Headphones", category: "Audio", price: "₹4,999", tone: "mint" },
  { icon: "⌚", name: "Pulse Smartwatch S2", category: "Wearables", price: "₹6,499", tone: "blue" },
  { icon: "⌨️", name: "KeyLite Mechanical", category: "Accessories", price: "₹3,299", tone: "peach" },
];

export default function Home() {
  const [view, setView] = useState<View>("home");
  const [selected, setSelected] = useState<Product>(products[0]);
  const [ordered, setOrdered] = useState(false);
  const [orderContext, setOrderContext] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { from: "ai", text: "Hi! I’m ShopX AI Support. I can help with orders, delivery, returns and refunds." },
  ]);

  function navigate(next: View) { setView(next); }
  function buy(product: Product) { setSelected(product); setView("checkout"); }
  function placeOrder() { setOrdered(true); setView("confirmed"); }

  function openOrderSupport() {
    setOrderContext(true);
    setView("support");
    setMessages([
      { from: "ai", text: "I’ve linked Order #SX240731 to this chat, so you don’t need to repeat the details.", meta: "Order context loaded" },
      { from: "ai", text: "I can see the package is delayed at the Coimbatore sorting hub. What problem are you facing?" },
    ]);
  }

  function answerIssue(text: string) {
    const lower = text.toLowerCase();
    let reply = "I understand. I’ve checked Order #SX240731 and the latest delivery information for you.";
    let meta = "AI checked order data";
    if (lower.includes("late") || lower.includes("where") || lower.includes("delay")) {
      reply = "Your package was delayed at the Coimbatore sorting hub due to a courier backlog. The updated delivery date is 10 Aug. No action is needed from you right now.";
      meta = "Resolved by AI • High confidence";
    } else if (lower.includes("damage") || lower.includes("human") || lower.includes("agent")) {
      reply = "A damaged item needs a human review. I’ve created support ticket #SUP-1042 and passed this order and our conversation to an agent. You won’t need to explain it again.";
      meta = "Escalated to human • Ticket #SUP-1042";
    } else if (lower.includes("refund") || lower.includes("return")) {
      reply = "This order is eligible for a return within 7 days of delivery. I can start the return after the package is delivered. If the item arrives damaged, I’ll escalate it immediately.";
      meta = "Policy + order data checked";
    }
    setMessages((current) => [...current, { from: "user", text }, { from: "ai", text: reply, meta }]);
    setDraft("");
  }

  function sendMessage(event: FormEvent) { event.preventDefault(); if (draft.trim()) answerIssue(draft.trim()); }
  const navView = view === "checkout" || view === "confirmed" ? "products" : view;

  return <main>
    <header className="topbar">
      <button className="brand" onClick={() => navigate("home")} aria-label="ShopX home"><span className="brand-mark">S</span><span>ShopX</span></button>
      <nav aria-label="Main navigation">{(["home", "products", "orders", "support"] as View[]).map((item) => <button key={item} className={navView === item ? "nav-active" : ""} onClick={() => navigate(item)}>{item === "support" ? "Help & Support" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
      <div className="header-actions"><button aria-label="Cart">Bag <span>{ordered ? 1 : 0}</span></button><div className="avatar">SR</div></div>
    </header>

    {view === "home" && <section className="hero">
      <div className="hero-copy"><span className="eyebrow">SHOP • ORDER • GET INSTANT SUPPORT</span><h1>Shop normally.<br/><em>Get help instantly.</em></h1><p>ShopX is our demo store showing how an existing shopping app can integrate our AI customer-support platform.</p><div className="hero-buttons"><button className="primary" onClick={() => navigate("products")}>Start demo purchase →</button><button className="secondary" onClick={() => navigate("orders")}>View demo order</button></div><div className="trust"><span>1. Place order</span><span>2. Face a problem</span><span>3. Ask AI support</span></div></div>
      <div className="hero-art"><div className="headphone">🎧</div><div className="floating-card"><small>DEMO PRODUCT</small><strong>Orbit Pro</strong><span>Use this product to try the complete support flow.</span><b>₹4,999</b></div></div>
    </section>}

    {view === "products" && <section className="section page"><span className="eyebrow">STEP 1 • CUSTOMER SHOPS</span><h1>Choose a product</h1><p className="page-lead">For the prototype, purchase any item and continue to the order flow.</p><div className="product-grid">{products.map((p) => <article className="product" key={p.name}><div className={`product-image ${p.tone}`}>{p.icon}<span>★ 4.8</span></div><small>{p.category}</small><h3>{p.name}</h3><div><strong>{p.price}</strong><button className="buy-button" onClick={() => buy(p)} aria-label={`Buy ${p.name}`}>Buy now</button></div></article>)}</div></section>}

    {view === "checkout" && <section className="flow-page"><div className="flow-steps"><span className="done">1 Product</span><i>→</i><span className="active">2 Checkout</span><i>→</i><span>3 Order</span><i>→</i><span>4 Support</span></div><div className="checkout-grid"><div><span className="eyebrow">STEP 2 • PLACE DEMO ORDER</span><h1>Checkout</h1><div className="address-card"><small>DELIVER TO</small><strong>Sree Ram</strong><p>Singanallur, Coimbatore, Tamil Nadu 641005</p><button>Change</button></div><div className="payment-card"><small>PAYMENT METHOD</small><strong>Demo payment</strong><p>No real payment will be processed.</p><span>✓ Prototype mode</span></div></div><aside className="summary-card"><h3>Order summary</h3><div className={`summary-product ${selected.tone}`}><span>{selected.icon}</span><div><strong>{selected.name}</strong><small>Qty 1</small></div></div><div className="summary-row"><span>Product</span><b>{selected.price}</b></div><div className="summary-row"><span>Delivery</span><b>FREE</b></div><div className="summary-total"><span>Total</span><strong>{selected.price}</strong></div><button className="primary full" onClick={placeOrder}>Place demo order</button><small className="safe-note">This is a prototype. No payment is taken.</small></aside></div></section>}

    {view === "confirmed" && <section className="confirmed"><div className="success-mark">✓</div><span className="eyebrow">ORDER PLACED</span><h1>Order confirmed!</h1><p>Order <strong>#SX240731</strong> has been created for the prototype.</p><div className="mini-order"><span>{selected.icon}</span><div><strong>{selected.name}</strong><small>Expected delivery: 9 Aug</small></div></div><button className="primary" onClick={() => navigate("orders")}>Track this order →</button></section>}

    {view === "orders" && <section className="section page"><span className="eyebrow">STEP 3 • CUSTOMER SEES A PROBLEM</span><h1>My Orders</h1><p className="page-lead">This demo order has a delivery issue so we can show the AI support flow.</p><article className="order-card problem"><div className="order-icon">🎧</div><div><small>ORDER #SX240731</small><h3>{ordered ? selected.name : "Orbit Pro Headphones"}</h3><p>Ordered 7 Aug • Expected 9 Aug</p><div className="track"><span className="passed">✓ Ordered</span><span className="passed">✓ Shipped</span><span className="warning">! Delayed</span><span>Delivery</span></div><div className="problem-note"><b>Delivery delayed</b><span>Your package is held at the Coimbatore sorting hub.</span></div></div><div className="order-status"><span className="late">● Needs attention</span><button className="support-cta" onClick={openOrderSupport}>Get help with this order →</button></div></article></section>}

    {view === "support" && <section className="support-flow"><div className="support-info"><span className="eyebrow">STEP 4 • CUSTOMER ASKS FOR HELP</span><h1>AI Order Support</h1><p>The customer enters support directly from the affected order. The AI receives the order context automatically.</p>{orderContext ? <div className="linked-order"><div className="order-icon small">🎧</div><div><small>LINKED ORDER</small><strong>#SX240731 • Orbit Pro Headphones</strong><span>⚠ Delivery delayed • Coimbatore hub</span></div><b>Context sent to AI ✓</b></div> : <button className="primary" onClick={openOrderSupport}>Load demo order into support</button>}<div className="demo-hint"><strong>Try both prototype outcomes:</strong><span>“My delivery is late” → AI resolves it</span><span>“My item arrived damaged” → AI escalates to a human</span></div></div><div className="support-chat-card"><div className="chat-head inline"><div className="ai-logo">✦</div><div><strong>ShopX AI Support</strong><span><i></i> Connected to support platform</span></div></div><div className="messages large">{messages.map((m, i) => <div key={i} className={`message ${m.from}`}>{m.text}{m.meta && <small className="message-meta">✓ {m.meta}</small>}</div>)}</div><div className="quick"><button onClick={() => answerIssue("My delivery is late")}>My delivery is late</button><button onClick={() => answerIssue("My item arrived damaged")}>Item arrived damaged</button><button onClick={() => answerIssue("Can I return this order?")}>Return question</button></div><form className="support-form" onSubmit={sendMessage}><input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Describe your problem…" aria-label="Chat message"/><button type="submit">Send</button></form><small className="chat-note">Prototype responses are mocked until Person 2&apos;s backend API is connected.</small></div></section>}

    {view !== "support" && <button className="chat-fab" onClick={() => navigate("support")} aria-label="Open AI support"><span>✦</span><div><strong>Need help?</strong><small>Ask ShopX AI</small></div></button>}
  </main>;
}
