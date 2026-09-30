# Delivery Acknowledgement — questions for Alex

Sent after the 2026-08-13 demo. Alex asked for (a) a minimal customer
acknowledgement view and (b) a way for it to work at remote sites with no
connectivity. These questions decide the design; we are not building until they
are answered.

---

Hi Alex,

Following up on the delivery acknowledgement you raised — we've scoped it and
it's very doable. Before we build, there are a few things only you can answer,
because they change the design significantly.

**First, one thing worth explaining**, because it shapes everything else.

An acknowledgement app can absolutely work with no signal at the delivery — the
scans are stored on the phone and upload themselves once it next gets a
connection. But the app has to reach the phone in the first place, and that
needs a connection *once*, at setup.

So the requirement isn't internet at the delivery. It's **internet once, ever,
on that phone** — before it goes out to the remote site. After that it works
offline indefinitely.

That gives us the questions below.

### 1. Whose phone does the scanning?

If deliveries go out with a freight carrier rather than your own truck, we can't
put anything on the driver's device — so it would be the **receiving person at
the customer's site**.

Do the people receiving goods at your remote sites have work smartphones, and
would their IT allow installing an app on them?

### 2. Can that phone get a connection at least once?

Not at the delivery — just at some point. Setup before travelling out, a trip
into town, a site office with occasional satellite. Any one of those is enough.

### 3. iPhone or Android at those sites?

This matters more than it sounds. iPhones can clear an app's stored data if the
app hasn't been opened for about a week, which is a genuine risk for a phone
that captures a delivery and then sits unused. We can work around it, but we'd
want to know what we're targeting.

### 4. If the answer to 1 or 2 is no — is this acceptable?

The receiving person signs the paperwork exactly as they do today, and then
someone scans the labels and enters them into the system later, from wherever
there's a connection — that evening, the next morning, whenever.

It isn't real time, but it needs no device at the delivery point and it cannot
fail. Would that be good enough for the genuinely disconnected sites?

### 5. Does this need to match a form you already file?

If the delivery receipt is a numbered QCF form that goes into your quality
records, we'd reproduce it exactly rather than replace it — same as we did with
the project schedule and the progress report.

### 6. Who needs to know, and how fast?

When a site has been offline, an acknowledgement might not reach us for a few
days. During that window nobody at Mercury knows whether the goods arrived.

Would a **"delivered, not yet acknowledged"** list be useful — so you can see at
a glance which shipments are still unconfirmed and chase them?

### 7. One more, on the scanning itself

When your customer receives seven items, is the acknowledgement expected to be
**item by item** — each unit scanned and confirmed individually — or is
confirming the shipment as a whole sufficient, with item detail only when
something is wrong?

Our assumption is item by item, since the units are already serialised and
labelled. Tell us if that's heavier than it needs to be.

---

Once we have these we'll come back with the design. Our expectation is to build
the connected version first so you can see it working end to end, then add the
offline capability — the answers above decide exactly what that second part
looks like.
