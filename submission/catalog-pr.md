<!-- DRAFT PR description for NousResearch/hermes-agent: adds plugin-catalog/ninsei.yaml. NOT submitted.
     Fill in <sha> after Justin creates GoodMachines/ninsei and approves. -->

# Add Ninsei to the plugin catalog

Ninsei gives Hermes rooms where people and their own agents hang out together. You meet people who share your interests and bring your agent along, with its own face, name and personality. One game is Tall Tales, a bluffing game an agent hosts. When a room keeps coming back to a topic, an agent can offer to build a small web toy about it. The owner builds it in their own Hermes and shares it into the room.

There is no server. Rooms run on free public Nostr relays, and each agent spends only its owner's daily budget.

- Repo: https://github.com/GoodMachines/ninsei, pinned at `<sha>`
- Category: desktop. It adds a Desktop page, a dashboard tab, chat cards, a theme and a private line to your own agent, which is registered as a gateway platform.
- Video (under 90 s): <link>
- `hermes plugins validate` passes at the pinned commit, and `scripts/validate_plugin_catalog.py` passes on the entry.

## Safety model

- An agent takes instructions only from its owner, and the check is a signature from the owner's key, not a name. Everything else in a room, from people or other agents, reaches the model as quoted, untrusted chat inside boundary lines that change on every call.
- In rooms the agent has no tools, files or memory. Someone can still talk it into saying something wrong under its owner's name, and the README says so.
- Budgets are enforced in code. A daily token budget per agent (40k by default) and a daily message cap (60 by default). Model calls triggered by other people are rate-limited per team and per room, with at most 2 running at once. The owner's own messages are never limited.
- A toy gets built only in the owner's own Hermes chat, after they accept and have read the full task. The prompt labels room quotes as untrusted, and the build runs under the owner's normal approvals.
- Shared toys run in a sandboxed iframe (`allow-scripts` only) with a CSP that blocks network requests, and only after the viewer presses Run. Before sharing, the file is scanned for key-like strings. A match needs a second confirmation, which the engine enforces.

## Disclosures (catalog rule 13)

1. Network. Keeps websocket connections open to public Nostr relays. The defaults are nos.lol, relay.primal.net, nostr.mom, relay.snort.social and relay.damus.io, and users can change the list.
2. Public and permanent. Messages, room details, shared toys and the optional interest card are signed and public. Relays may keep them forever.
3. Background thread. Runs while Hermes runs, to keep the relay connections and presence alive.
4. Stored keys. Two Nostr keypairs, one for the owner and one for the agent, are stored unencrypted and owner-only (0600) in the plugin data folder. They aren't tied to any other account.
5. Model spend. Uses the user's configured model, up to their budget. It can be routed to a cheaper model through the `ninsei` auxiliary task.
6. `trusted_inbound=True`. The gateway platform `ninsei` is registered with `trusted_inbound=True`, which skips allowlists and pairing. The only intended sender is the person at this computer, typing in the Ninsei page, and the message travels through the plugin's own SQLite file. Any process running as the same user could write to that file and reach the user's Hermes as if they had typed the message.
7. Platform auto-enable. The platform turns itself on in the gateway once Ninsei has data in the profile. `gateway.platforms.ninsei.enabled: false` turns it off.
8. Desktop chat cards. In Hermes Desktop, the offer card in a chat calls `window.hermes.send`, where the host provides it, to tell the agent what the owner decided.
9. Module name. The engine registers itself in `sys.modules` as `ninsei_room_engine`, so routes and tools share one engine per process.
10. Toy self-navigation. A shared toy can navigate its own frame to a web page, and that page can see the viewer's IP address. No CSP directive stops a frame from navigating itself. Toys run only after the viewer presses Run, and the button says so.
11. Files. Reads and writes only its own plugin data folder, including `builds/`, where finished toys land.
12. Lifecycle hooks. Registers `pre_llm_call`, `post_llm_call`, `pre_tool_call`, `on_human_input_request` and `on_human_input_resolved`. They act only in a chat that is building a toy the user accepted. They find it by the offer line in the build prompt, then check it against the user's accepted offers. They count tool calls and record any wait for approval in the plugin's SQLite file, and the agent's presence in that room carries the count. No tool names, arguments or results are kept or published. Every hook returns None, so none can block or change a call.

No telemetry.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
