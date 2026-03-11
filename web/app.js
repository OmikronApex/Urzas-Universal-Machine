const $ = (sel) => document.querySelector(sel);

const connStatus = $("#connStatus");
const lastPhase = $("#lastPhase");

const hudStep = $("#hud-step");
const hudState = $("#hud-state");
const hudHead = $("#hud-head");
const hudHalted = $("#hud-halted");

const scenarioSelect = $("#scenarioSelect");
const btnReset = $("#btnReset");
const btnFrame = $("#btnFrame");
const btnStep = $("#btnStep");
const compileInput = $("#compileInput");
const assemblerInput = $("#assemblerInput");

const chkAutoplay = $("#chkAutoplay");
const speed = $("#speed");
const radius = $("#radius");

const battlefieldRow = $("#battlefieldRow");
const bobPermanentsRow = $("#bobPermanentsRow");
const aliceBattlefieldRow = $("#aliceBattlefieldRow"); // Ensure this matches your index.html ID
const stackPile = $("#stackPile");
const graveyardList = $("#graveyardList");
const logLines = $("#logLines");
const handZone = $("#handZone");

let ws = null;

let currentSnapshot = null;
let currentFrame = null;

let autoplayTimer = null;

function wsUrl() {
    const proto = (location.protocol === "https:") ? "wss" : "ws";
    return `${proto}://${location.host}/ws`;
}

function send(msg) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(msg));
}

function setConn(text, ok) {
    connStatus.textContent = text;
    connStatus.style.color = ok ? "rgba(87,211,138,0.95)" : "rgba(255,89,100,0.95)";
}

function clearAutoplay() {
    if (autoplayTimer) {
        clearInterval(autoplayTimer);
        autoplayTimer = null;
    }
}

function stopAutoplayBecauseHalted() {
    if (!chkAutoplay.checked) return;
    clearAutoplay();
    chkAutoplay.checked = false;

    const div = document.createElement("div");
    div.textContent = "AUTOPLAY stopped: machine is halted.";
    div.style.color = "rgba(224,193,90,0.95)";
    logLines.prepend(div);
}

function startAutoplay() {
    clearAutoplay();
    // Invert the speed: 100 on slider = 0ms delay, 0 on slider = 1000ms delay
    const sliderVal = Number(speed.value);
    const maxDelay = 1000;
    const delay = maxDelay - (sliderVal * 10);

    autoplayTimer = setInterval(() => {
        send({type: "step_step"}); // Changed from step_frame to step_step
    }, delay);
}

function updateHud(snapshot) {
    hudStep.textContent = `STEP: ${snapshot?.step_index ?? "-"}`;
    hudState.textContent = `STATE: ${snapshot?.state ?? "-"}`;
    hudHead.textContent = `HEAD: ${snapshot?.head ?? "-"}`;
    hudHalted.textContent = `HALTED: ${snapshot?.halted ?? "-"}`;
    hudHalted.style.color = snapshot?.halted ? "rgba(255,89,100,0.95)" : "rgba(231,238,247,0.7)";
}

function tokenCard({pos, tok, isHead, blankSymbol, gainsAttached, flashClass, isAttachment = false}) {
    const el = document.createElement("div");
    el.className = "card";
    if (isAttachment) el.classList.add("attached");

    // Use specific name if provided in tok, otherwise fallback to "Illusory Gains" for attachments or blankSymbol
    const creatureType = tok?.creature_type ?? (isAttachment ? "Illusory Gains" : blankSymbol);

    // Determine the visual color class
    let color = tok?.color ?? "white";
    const nameLower = creatureType.toLowerCase();

    // Map specific names to canonical MTG colors (Overriding the token's move-color)
    if (nameLower.includes("infest") ||
        nameLower.includes("dread of night") ||
        nameLower.includes("soul snuffers")) {
        color = "black";
    } else if (nameLower.includes("illusory gains")) {
        color = "blue";
    } else if (nameLower.includes("cleansing beam") ||
        nameLower.includes("wild evocation")) {
        color = "red";
    } else if (nameLower.includes("choke") ||
        nameLower.includes("vigor") ||
        nameLower.includes("steely resolve") ||
        nameLower.includes("prismatic omen") ||
        nameLower.includes("recycle")) {
        color = "green";
    } else if (nameLower.includes("coalition victory") ||
        nameLower.includes("ancient tomb")) {
        color = "gold";
    } else if (nameLower.includes("wheel of sun and moon") ||
        nameLower.includes("blazing archon") ||
        nameLower.includes("privileged position")) {
        color = "green/white";
    } else if (nameLower.includes("rotlung reanimator") ||
        nameLower.includes("xathrid necromancer")) {
        color = "black/green/white";
    } else if (nameLower.includes("mesmeric orb")) {
        color = "colorless";
    }

    const tapped = !!tok?.tapped || creatureType === "Ancient Tomb";
    const tokenId = tok?.token_id ?? 0;

    if (color === "white") el.classList.add("color-white");
    if (color === "green") el.classList.add("color-green");
    if (color === "blue") el.classList.add("color-blue");
    if (color === "black") el.classList.add("color-black");
    if (color === "red") el.classList.add("color-red");
    if (color === "gold") el.classList.add("color-gold");
    if (color === "green/white") el.classList.add("color-green-white");
    if (color === "black/green/white") el.classList.add("color-black-green-white");
    if (color === "colorless") el.classList.add("color-colorless");

    // ONLY highlight the main creature, never the attachment
    if (!isAttachment) {
        if (isHead) el.classList.add("head");
    }

    if (flashClass) el.classList.add(flashClass);

    const frame = document.createElement("div");
    frame.className = "card-frame";

    // Header: Name only
    const nameLine = document.createElement("div");
    nameLine.className = "name-line";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = creatureType;

    nameLine.appendChild(nameSpan);

    // Art Box (Image)
    const artBox = document.createElement("div");
    artBox.className = "art-box";

    const typeKey = creatureType.toLowerCase();
    // Complete mapping for creatures AND spells
    const artMap = {
        // Creatures
        "aetherborn": "aetherborn.jpg",
        "basilisk": "basilisk.jpg",
        "cephalid": "cephalid.jpg",
        "demon": "demon.jpg",
        "elf": "elf.jpg",
        "faerie": "faerie.jpg",
        "giant": "giant.jpg",
        "harpy": "harpy.jpg",
        "illusion": "illusion.jpg",
        "juggernaut": "juggernaut.jpg",
        "kavu": "kavu.jpg",
        "leviathan": "leviathan.jpg",
        "myr": "myr.jpg",
        "noggle": "noggle.jpg",
        "orc": "orc.jpg",
        "pegasus": "pegasus.jpg",
        "rhino": "rhino.jpg",
        "sliver": "sliver.jpg",
        "assassin": "assassin.jpg",
        "vigor": "vigor.jpg",
        "blazing archon": "blazing_archon.jpg",

        // Spells & Enchantments & Death Triggers
        "infest": "infest.jpg",
        "cleansing beam": "cleansing_beam.jpg",
        "coalition victory": "coalition_victory.jpg",
        "soul snuffers": "soul_snuffers.jpg",
        "illusory gains": "illusory_gains.jpg",
        "cloak of invisibility": "cloak_of_invisibility.jpg",
        "rotlung reanimator": "rotlung_reanimator.jpg",
        "xathrid necromancer": "xathrid_necromancer.jpg",
        "wild evocation": "wild_evocation.jpg",
        "wheel of sun and moon": "wheel_of_sun_and_moon.jpg",
        "dread of night": "dread_of_night.jpg",
        "steely resolve": "steely_resolve.jpg",
        "mesmeric orb": "mesmeric_orb.jpg",
        "ancient tomb": "ancient_tomb.jpg",
        "prismatic omen": "prismatic_omen.jpg",
        "choke": "choke.jpg",
        "recycle": "recycle.jpg",
        "privileged position": "privileged_position.jpg",
    };

    let matchedArt = null;
    // Check for exact or partial matches in the artMap
    for (const [key, filename] of Object.entries(artMap)) {
        if (typeKey === key || typeKey.includes(key)) {
            matchedArt = `/static/images/${filename}`;
            break;
        }
    }

    if (matchedArt) {
        artBox.style.backgroundImage = `url('${matchedArt}')`;
        artBox.textContent = "";
    } else {
        artBox.textContent = (isHead && !isAttachment) ? "👁️" : "✨";
    }

    // Type Line
    const typeLine = document.createElement("div");
    typeLine.className = "type-line";
    if (isAttachment || nameLower.includes("illusory gains") || nameLower.includes("wheel of sun and moon") || nameLower.includes("cloak of invisibility")) {
        typeLine.textContent = "Enchantment - Aura";
    } else if (nameLower.includes("wild evocation") || nameLower.includes("dread of night") || nameLower.includes("steely resolve") || nameLower.includes("prismatic omen") || nameLower.includes("choke") || nameLower.includes("recycle")|| nameLower.includes("privileged position")) {
        typeLine.textContent = "Enchantment";
    } else if (nameLower.includes("mesmeric orb")) {
        typeLine.textContent = "Artifact";
    } else if (nameLower.includes("ancient tomb")) {
        typeLine.textContent = "Land";
    } else if (nameLower.includes("infest") || nameLower.includes("cleansing beam") || nameLower.includes("coalition victory")) {
        typeLine.textContent = "Sorcery";
    } else if (nameLower.includes("rotlung reanimator")) {
        typeLine.textContent = "Creature - Zombie Cleric";
    } else if (nameLower.includes("xathrid necromancer")) {
        typeLine.textContent = "Creature - Human Wizard";
    } else if (nameLower.includes("vigor")) {
        typeLine.textContent = "Creature - Elemental Incarnation";
    } else {
        typeLine.textContent = `Token Creature - ${creatureType}`;
    }

    // Specific override for non-token named creatures


    // Text Box
    const textBox = document.createElement("div");
    textBox.className = "text-box";
    if (nameLower.includes("cloak of Invisibility")) {
        textBox.innerHTML = "Enchanted creature has phasing.";
    } else if (nameLower.includes("illusory gains")) {
        textBox.innerHTML = "You control enchanted creature.";
    } else if (nameLower.includes("infest")) {
        textBox.innerHTML = "All creatures get -2/-2 until end of turn.";
    } else if (nameLower.includes("cleansing beam")) {
        textBox.innerHTML = "Cleansing Beam deals 2 damage to target creature and each other creature that shares a color with it.";
    } else if (nameLower.includes("coalition victory")) {
        textBox.innerHTML = "You win the game if you control a land of each basic land type and a creature of each color.";
    } else if (nameLower.includes("soul snuffers")) {
        textBox.innerHTML = "When Soul Snuffers enters the battlefield, put a -1/-1 counter on each creature.";
    } else if (nameLower.includes("wild evocation")) {
        textBox.innerHTML = "At upkeep: Cast random card from hand if able.";
    } else if (nameLower.includes("dread of night")) {
        textBox.innerHTML = "Black creatures get -1/-1.";
    } else if (nameLower.includes("steely resolve")) {
        textBox.innerHTML = "Assembly Workers have shroud.";
    } else if (nameLower.includes("vigor")) {
        textBox.innerHTML = "Turn Damage to creature into +1/+1 counters.";
    } else if (nameLower.includes("mesmeric orb")) {
        textBox.innerHTML = "Whenever a permanent becomes untapped, its controller mills a card.";
    } else if (nameLower.includes("ancient tomb")) {
        textBox.innerHTML = "Tap: Add {C}{C}. Ancient Tomb deals 2 damage to you.";
    } else if (nameLower.includes("prismatic omen")) {
        textBox.innerHTML = "Lands you control are every basic land type.";
    } else if (nameLower.includes("choke")) {
        textBox.innerHTML = "Islands don't untap during their controllers' untap steps.";
    } else if (nameLower.includes("blazing archon")) {
        textBox.innerHTML = "Creatures can't attack you.";
    } else if (nameLower.includes("wheel of sun and moon")) {
        textBox.innerHTML = "Cards don't go to enchanted players graveyard, but bottom of library.";
    } else if (nameLower.includes("recycle")) {
        textBox.innerHTML = "Skip your draw step";
    } else if (nameLower.includes("privileged position")) {
        textBox.innerHTML = "Other permanents you control have hexproof.";
    } else if (nameLower.includes("cloak of invisibility")) {
        textBox.innerHTML = "Enchanted creature has phasing.";
    } else {
        textBox.innerHTML = "";
    }

    frame.appendChild(nameLine);
    frame.appendChild(artBox);
    frame.appendChild(typeLine);
    frame.appendChild(textBox);

    // P/T Box (Creatures only)
    const typeLineText = typeLine.textContent.toLowerCase();
    const isCreature = typeLineText.includes("creature");

    if (!isAttachment && isCreature) {
        const ptBox = document.createElement("div");
        ptBox.className = "pt-box";

        // Proper strength and toughness
        let ptValue = 1;
        const typeLower = creatureType.toLowerCase();

        if (typeLower.includes("soul snuffers")) {
            // Soul Snuffers is a base 3/3
            ptValue = 3;
        } else if (typeLower.includes("blazing archon") || typeLower.includes("vigor")) {
            ptValue = 6;
        } else if (typeof pos === 'number' && currentSnapshot) {
            // Bob's tokens use the symmetric progression based on distance from Head
            const head = currentSnapshot.head ?? 0;
            ptValue = 2 + Math.abs(head - pos);
        }

        ptBox.textContent = `${ptValue}/${ptValue}`;
        frame.appendChild(ptBox);
    }

    el.appendChild(frame);
    el.title = isAttachment ? "Illusory Gains" : `Position ${pos}\nType: ${creatureType}\nToken: #${tokenId}`;

    return el;
}

function render(snapshot, frame, graveyardData = [], stackData = []) {
    if (!snapshot) return;

    updateHud(snapshot);

    // --- Bob's Global Permanents (The Trigger Engine) ---
    if (bobPermanentsRow) {
        bobPermanentsRow.innerHTML = "";
        // Use frame's list if present, otherwise fallback to snapshot's list
        const phasedOutList = (frame && frame.phased_out && frame.phased_out.length > 0) 
                                  ? frame.phased_out 
                                  : (snapshot.phased_out || []);

        const engineConfigs = [
            {name: "Rotlung Reanimator", count: 15, state: "q1"},
            {name: "Rotlung Reanimator", count: 14, state: "q2"},
            {name: "Xathrid Necromancer", count: 4, state: "q1"},
            {name: "Xathrid Necromancer", count: 3, state: "q2"},
            {name: "Wild Evocation", count: 1},
            {name: "Recycle", count: 1},
            {name: "Privileged Position", count: 1},
            {name: "Vigor", count: 1},
            {name: "Blazing Archon", count: 1}
        ];

        engineConfigs.forEach(config => {
            const stackContainer = document.createElement("div");
            stackContainer.className = "card-stack";
            //stackContainer.style.transform = "scale(0.8)";
            stackContainer.style.marginRight = "-20px";

            for (let i = 0; i < config.count; i++) {
                const isBottom = (i === 0);
                const isTop = (i === config.count - 1);
                
                // Check if this specific state-group is phased out
                const isPhasedOut = config.state && phasedOutList.includes(config.state);

                const cardEl = tokenCard({
                    pos: "Engine",
                    tok: {creature_type: config.name, color: "white", tapped: false},
                    isHead: false,
                    blankSymbol: "Cephalid",
                    gainsAttached: false,
                    isAttachment: false
                });

                if (isPhasedOut) {
                    cardEl.classList.add("phased-out");
                }

                if (i > 0) {
                    cardEl.style.position = "absolute";
                    cardEl.style.top = `${i * 4}px`;
                    cardEl.style.left = `${i * 2}px`;
                    cardEl.style.zIndex = i * 2; // Leave room for attachments
                }

                // Disable hover for everything except the topmost card in the stack
                if (!isTop) {
                    cardEl.classList.add("no-hover");
                }

                stackContainer.appendChild(cardEl);

                // Add Cloak of Invisibility ONLY to the bottom-most card in the stack
                if (isBottom && (config.name.includes("Rotlung") || config.name.includes("Xathrid"))) {
                    const cloakEl = tokenCard({
                        pos: "Engine",
                        tok: {creature_type: "Cloak of Invisibility", color: "blue"},
                        isHead: false,
                        blankSymbol: "Cephalid",
                        gainsAttached: false,
                        isAttachment: true
                    });

                    cloakEl.style.zIndex = 0; // Place behind the bottom card
                    cloakEl.style.pointerEvents = "auto";
                    stackContainer.appendChild(cloakEl);
                }
            }
            bobPermanentsRow.appendChild(stackContainer);
        });
    }

    const tape = snapshot.tape || {};
    const head = snapshot.head ?? 0;
    const blankSymbol = "Cephalid";
    const radiusN = Number(radius.value);

    const lo = head - radiusN;
    const hi = head + radiusN;

    const changedPositions = new Set((frame?.changed_positions || []).map((x) => Number(x)));
    const writtenPos = (frame?.written_pos !== undefined && frame?.written_pos !== null) ? Number(frame.written_pos) : null;
    const readPos = (frame?.read_pos !== undefined && frame?.read_pos !== null) ? Number(frame.read_pos) : null;

    battlefieldRow.innerHTML = "";
    for (let pos = lo; pos <= hi; pos++) {
        // Calculate paper-invariant color: Green for left of head, White for head and right
        const defaultColor = (pos < head) ? "green" : "white";
        const tok = tape[String(pos)] || {creature_type: blankSymbol, color: defaultColor, tapped: false, token_id: 0};
        const isHead = pos === head;
        const gainsAttached = (snapshot.illusory_gains_attached_to != null) && (tok.token_id === snapshot.illusory_gains_attached_to);
        const tapped = !!tok?.tapped;

        const stackContainer = document.createElement("div");
        stackContainer.className = "card-stack";
        if (tapped) stackContainer.classList.add("tapped");

        let flashClass = null;
        if (writtenPos === pos) flashClass = "flash-new";
        else if (readPos === pos) flashClass = "flash-died";
        else if (changedPositions.has(pos)) flashClass = "flash-new";

        // Add the main token
        stackContainer.appendChild(tokenCard({pos, tok, isHead, blankSymbol, gainsAttached, flashClass}));

        // Add Illusory Gains as a separate card if attached
        if (gainsAttached) {
            stackContainer.appendChild(tokenCard({
                pos,
                tok: {creature_type: "Illusory Gains", color: "blue"},
                isHead,
                blankSymbol,
                gainsAttached: false,
                isAttachment: true
            }));
        }

        battlefieldRow.appendChild(stackContainer);
    }

    // --- Alice Battlefield ---
    if (aliceBattlefieldRow) {
        aliceBattlefieldRow.innerHTML = "";
        // Look for battlefield data in the snapshot payload
        const aliceCards = snapshot.alice_battlefield || [];

        // Tracking for stacking duplicate cards
        const counts = {};

        aliceCards.forEach((cardName) => {
            counts[cardName] = (counts[cardName] || 0) + 1;
            const index = counts[cardName] - 1;
            const isAncientTomb = cardName === "Ancient Tomb";

            const stackContainer = document.createElement("div");
            stackContainer.className = "card-stack";
            if (isAncientTomb) stackContainer.classList.add("tapped");

            const cardEl = tokenCard({
                pos: "Alice's Board",
                tok: {creature_type: cardName, color: "white", tapped: isAncientTomb},
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false
            });

            // If it's a duplicate, stack it with an offset
            if (index > 0) {
                stackContainer.style.marginLeft = "-120px";
                stackContainer.style.marginTop = `${index * 15}px`;
                stackContainer.style.zIndex = index;
            }

            stackContainer.appendChild(cardEl);
            aliceBattlefieldRow.appendChild(stackContainer);
        });
    }

    // --- Stack - Use stackData from server ---
    stackPile.innerHTML = "";
    const stack = stackData || [];
    if (stack.length === 0) {
        stackPile.innerHTML = `<div style="color: rgba(231,238,247,0.45); padding: 20px; text-align: center; width: 100%;">(empty)</div>`;
    } else {
        const stackContainer = document.createElement("div");
        stackContainer.className = "card-stack stack-pile-visual";

        for (let i = 0; i < stack.length; i++) {
            const isTop = (i === stack.length - 1);
            const spellEl = tokenCard({
                pos: "",
                tok: {creature_type: stack[i], color: "white"},
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false
            });

            spellEl.classList.add("stack-item");

            if (!isTop) {
                spellEl.classList.add("attached");
                // Stagger every item behind the one above it
                const offset = (stack.length - 1 - i) * 26;
                spellEl.style.top = `-${offset}px`;
                spellEl.style.zIndex = i;
            } else {
                spellEl.style.zIndex = stack.length;
                spellEl.style.top = "0px";
            }
            stackContainer.appendChild(spellEl);
        }
        stackPile.appendChild(stackContainer);
    }

    // --- Graveyard (Stack of cards) - Use graveyardData from server ---
    graveyardList.innerHTML = "";
    if (!graveyardData || graveyardData.length === 0) {
        graveyardList.innerHTML = `<div style="color: rgba(231,238,247,0.45); padding: 20px; text-align: center; width: 100%;">(empty)</div>`;
    } else {
        const pileContainer = document.createElement("div");
        pileContainer.className = "graveyard-stack";

        graveyardData.forEach((card, index) => {
            const cardEl = tokenCard({
                pos: "",
                tok: card, // card now contains {creature_type, color, token_id}
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false
            });
            cardEl.classList.add("graveyard-item");

            const rot = (index % 2 === 0 ? 1 : -1) * (index * 1.5);
            cardEl.style.top = `${index * 2}px`;
            cardEl.style.left = `${index * 1}px`;
            cardEl.style.transform = `rotate(${rot}deg)`;
            cardEl.style.zIndex = index;

            pileContainer.appendChild(cardEl);
        });
        graveyardList.appendChild(pileContainer);
    }

    // --- Hand Rendering ---
    if (handZone) {
        handZone.innerHTML = "";
        const hand = snapshot.cards_on_hand || [];
        hand.forEach((cardName) => {
            const cardEl = tokenCard({
                pos: "Hand",
                tok: {creature_type: cardName, color: "white", token_id: 0},
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false
            });
            handZone.appendChild(cardEl);
        });
    }

    // Narration / log
    if (frame?.narration && frame.narration.length) {
        for (const s of frame.narration) {
            const div = document.createElement("div");
            div.textContent = s;
            logLines.prepend(div);
        }
    }
    // keep last 80
    while (logLines.children.length > 80) {
        logLines.removeChild(logLines.lastChild);
    }

    lastPhase.textContent = frame?.phase ? `Phase: ${frame.phase}` : "";
}

function connect() {
    ws = new WebSocket(wsUrl());

    ws.addEventListener("open", () => {
        setConn("Connected", true);
        send({type: "ping"});
    });

    ws.addEventListener("close", () => {
        setConn("Disconnected", false);
        clearAutoplay();
        chkAutoplay.checked = false;
        setTimeout(connect, 600);
    });

    // Update message listeners to pass stack data
    ws.addEventListener("message", (ev) => {
        let msg = null;
        try {
            msg = JSON.parse(ev.data);
        } catch {
            return;
        }

        if (msg.type === "scenario_list") {
            const scenarios = msg.scenarios || [];
            const selected = msg.selected || null;
            scenarioSelect.innerHTML = "";
            for (const s of scenarios) {
                const opt = document.createElement("option");
                opt.value = s;
                opt.textContent = s;
                if (selected && selected === s) opt.selected = true;
                scenarioSelect.appendChild(opt);
            }
            return;
        }

        if (msg.type === "state") {
            currentSnapshot = msg.snapshot;
            currentFrame = {stack: [], narration: [], changed_positions: []};
            render(currentSnapshot, currentFrame, msg.graveyard, msg.stack); // Pass stack

            if (currentSnapshot?.halted) {
                stopAutoplayBecauseHalted();
            }
            return;
        }

        if (msg.type === "frame") {
            currentFrame = msg.frame;
            currentSnapshot = msg.snapshot;
            render(currentSnapshot, currentFrame, msg.graveyard, msg.stack); // Pass stack

            if (currentSnapshot?.halted) {
                stopAutoplayBecauseHalted();
            }
            return;
        }

        if (msg.type === "error") {
            const div = document.createElement("div");
            div.textContent = `ERROR: ${msg.message}`;
            div.style.color = "rgba(255,89,100,0.95)";
            logLines.prepend(div);
            return;
        }
    });
}

// UI wiring
btnReset.addEventListener("click", () => {
    // Local graveyardCards variable is gone, server handles reset
    send({type: "reset"});
});
btnFrame.addEventListener("click", () => send({type: "step_frame"}));
btnStep.addEventListener("click", () => send({type: "step_step"}));

scenarioSelect.addEventListener("change", () => {
    send({type: "load_scenario", name: scenarioSelect.value});
    graveyardList.innerHTML = "";
    logLines.innerHTML = "";
});

chkAutoplay.addEventListener("change", () => {
    if (chkAutoplay.checked) startAutoplay();
    else clearAutoplay();
});

speed.addEventListener("input", () => {
    if (chkAutoplay.checked) startAutoplay();
});

radius.addEventListener("input", () => {
    render(currentSnapshot, currentFrame);
});

// Start
connect();