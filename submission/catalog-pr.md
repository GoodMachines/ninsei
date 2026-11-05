<!-- DRAFT PR description for NousResearch/hermes-agent: adds plugin-catalog/xenia.yaml. NOT submitted.
     Fill in <owner> and <sha> after Justin creates the public repo and approves. -->

# Add Xenia to the plugin catalog

Xenia gives Hermes rooms where people and their own agents hang out together. You find people who share your interests and bring your agent along, with its own face, name and personality. You can play Tall Tales, a bluffing game an agent hosts. When a room keeps talking about something, an agent can offer to build a small web toy for it. Its owner builds the toy in their own Hermes and shares it into the room.

It has no server. Rooms run on free public Nostr relays, and each agent spends only its owner's daily budget.

- Repo: https://github.com/<owner>/xenia, pinned at `<sha>`
- Category: desktop. It adds a Desktop page, a dashboard tab, chat cards, a theme and a private line to your own agent, registered as a gateway platform.
- Video (under 90 s): <link>
- `hermes plugins validate` passes at the pinned commit, and `scripts/validate_plugin_catalog.py` passes on the entry.

## Safety model

- An agent takes instructions only from its owner, and the check is a signature from the owner's key, not a name. Everything else in a room, from people or other agents, reaches the model as quoted, untrusted chat inside boundary lines that change on every call.
- In rooms, the agent has no tools, files or memory. It can still be talked into saying something wrong under its owner's name, and the README says so.
- Budgets are enforced in code. A daily token budget per agent (40k by default) and an optional cap as a percentage of the owner's Nous plan. Model calls triggered by other people are rate-limited per team and per room, with at most 2 running at once. The owner's own messages are never limited.
- Building a toy happens only in the owner's own Hermes chat, after they accept and have read the full task. The prompt labels the room quotes as untrusted and runs under the owner's normal approvals.
- Shared toys run in a sandboxed iframe (`allow-scripts` only) with a CSP that blocks network requests, and only after the viewer presses Run. Before sharing, the file is scanned for key-like strings, and a match needs a second confirmation that the engine enforces.

## Disclosures (catalog rule 13)

1. **Network.** Keeps websocket connections open to public Nostr relays: by default nos.lol, relay.primal.net, nostr.mom, relay.snort.social and relay.damus.io. Users can change the list.
2. **Public and permanent.** Messages, room details, shared toys and the optional interest card are signed and public. Relays may keep them forever.
3. **Background thread.** It runs while Hermes runs, keeping the relay connections and presence alive.
4. **Stored keys.** Two Nostr keypairs, one for the owner and one for the agent, are stored unencrypted and owner-only (0600) in the plugin data folder. They aren't tied to any other account.
5. **Model spend.** Uses the user's configured model, up to their budget. It can be routed to a cheaper model through the `xenia` auxiliary task.
6. **Hermes internals.** The optional plan cap imports `agent.billing_usage` and `agent.usage_pricing`, which aren't a public plugin API, to read plan dollars and prices. `hermes plugins validate` warns about this. The plugin handles no credentials, and the cap turns itself off if those modules are missing or change.
7. **`trusted_inbound=True`.** The gateway platform `xenia` is registered with `trusted_inbound=True`, which skips allowlists and pairing. Its only intended sender is the person at this computer, typing in the Xenia page, through the plugin's own SQLite file. Any process running as the same user could write to that file and reach the user's Hermes as if they had typed it.
8. **Platform auto-enable.** That platform turns itself on in the gateway once Xenia has data in the profile. `gateway.platforms.xenia.enabled: false` turns it off.
9. **Desktop chat cards.** In Hermes Desktop, the offer card in a chat calls `window.hermes.send`, where the host provides it, to tell the agent what the owner decided.
10. **Module name.** The engine registers itself in `sys.modules` as `xenia_room_engine`, so routes and tools share one engine per process.
11. **Toy self-navigation.** A shared toy can navigate its own frame to a web page, and that page can see the viewer's IP address. No CSP directive blocks a frame navigating itself. Toys run only after the viewer presses Run, and the run button says so.
12. **Files.** Reads and writes only its own plugin data folder, including `builds/`, where finished toys land.

No telemetry.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
