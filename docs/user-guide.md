# Neo Chat — User Guide (Operator)

A guide for shop-floor staff, technicians, and shift leads using Neo Chat
in the factory.

> **For IT / Admin:** [admin-guide.md](./admin-guide.md) · **System setup:**
> [deploy/README-ONPREM.md](../deploy/README-ONPREM.md)

---

## What Neo Chat can do

- **Q&A** over machine manuals, SOPs, and repair history — answers come
  with **source citations**
- **Search documents** in the system and open PDFs right in the browser
- **Send feedback** when an answer is wrong or incomplete
- **Machines** — view/manage the machine registry (write access)

> Neo Chat is **not** a SCADA system — it doesn't show live sensor data.
> Anything about machine risk comes from **repair history** only.

---

## First-time login

1. Open a browser (Chrome / Edge recommended) and go to the URL IT gave
   you, e.g. `http://spark.lan`
2. On the **Login** page, enter the username/password an admin created for
   you, or click **Sign in with Google** (if the factory has it enabled)
3. Pick a **Factory** from the sidebar if you have access to more than one
4. You'll land on **Chat** or another page depending on your permissions

### Demo accounts (testing only — change these in production)

| Username | Password | Access |
|----------|----------|--------|
| `admin` | `changeme` | all factories, admin |
| `operator_f01` | `changeme` | F-01, read-only |

These only exist if someone has actually seeded them — there is no
working one-shot seed script for this in the current branch (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md#quick-bootstrap) and
[`docs/demo_playbook.md`](./demo_playbook.md#before-the-demo) for how to
create a first admin account manually if these credentials don't work).

---

## Main menu

| Menu | Access | What it's for |
|------|--------|-----------|
| **Chat with Neo** | everyone | AI Q&A with citations |
| **Machines** | write | view/manage the machine registry |
| **Documents** | everyone | browse documents you're allowed to see |
| **Upload Documents** | write + upload | send manuals/SOPs into the system |
| **Feedback** | everyone | report a wrong or incomplete answer |
| **Users & System** | admin | manage users (admin only) |
| **Manage Factories** | admin | configure factories (admin only) |

---

## Chatting with Neo — how to use it

### Ask a question

1. Go to **Chat with Neo**
2. Type your question in Thai or English, e.g.
   *"Servo MC-001 is running abnormally hot, what should I check first?"*
3. Click **Send** — the answer **streams in** word by word
4. Check the **citations** under the answer — click one to open the source
   document

### Tips for getting a good answer

- Include the **machine code** (e.g. MC-001) if it's about a specific machine
- Ask **one thing at a time** — don't combine multiple procedures in one
  sentence
- If there's nothing in the system, Neo will say **no data found** — don't
  guess yourself, ask an admin to upload the document instead

### Stopping an answer

Click **Stop** while Neo is answering, if the question was wrong or needs
changing.

### Chat history

- Past chats are in the left sidebar
- Click **New chat** to start a new topic

---

## Documents

1. Go to **Documents**
2. Pick a category / machine, or search by document name
3. Click a document to **open the PDF** in the browser
4. Documents you **don't have access to** (based on job position) won't
   show up

> Some factories enable **offline caching** — documents you've already
> opened may still be readable during a brief network outage.

---

## Uploading documents (technician / admin)

1. Go to **Upload Documents**
2. Drag a file (PDF, Excel, Word) into the box, or click to choose one
3. Select:
   - **Factory**
   - **Machine** (if relevant)
   - **Document type** (manual, SOP, repair history, …)
4. Click **Upload** — wait for status **completed** (can take several
   minutes for large files)
5. Check **Documents** to confirm it appears, and test it with a question
   in Chat

---

## Feedback

When Neo's answer is **wrong, incomplete, or cites the wrong document**:

1. Click **Feedback** under Neo's message (on the chat page)
2. Pick an issue type and describe it briefly
3. The admin team reviews it under **Feedback** and updates documents/ACLs
   as needed

---

## My Account

Under **My Account** (`/account`):

- View/edit your profile
- **Switch factory** (if you have access to more than one)
- Change your password (if enabled)
- Toggle **light/dark theme**

---

## PWA / installing to your home screen

On tablet or mobile (Chrome):

1. Open Neo Chat in the browser
2. Browser menu → **Add to Home Screen** / **Install app**
3. Launch it from the home-screen icon like a native app

---

## Troubleshooting

| Symptom | What to do |
|-------|-----------|
| Can't log in | Contact IT — check username / password / factory access |
| Chat doesn't respond / hangs | Refresh the page; if it's still stuck, ask IT to check `/readyz` |
| A document you expect isn't showing | Check your job position with an admin |
| Answer has no citation | There may be no data in the system — send feedback or ask an admin to upload it |
| Network drops | Cached documents may still be readable; chat requires a network connection |

**Never** put passwords or secrets in feedback.

---

## Related documents

| Document | For |
|--------|--------|
| [HANDOVER.md](./HANDOVER.md) | project handover |
| [admin-guide.md](./admin-guide.md) | admin guide |
| [README.md](../README.md) | system overview |
