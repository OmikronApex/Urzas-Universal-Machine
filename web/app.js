const $ = (sel) => document.querySelector(sel);

const connStatus = $("#connStatus");
const lastPhase = $("#lastPhase");

const hudStep = $("#hud-step");
const hudState = $("#hud-state");
const hudHead = $("#hud-head");
const hudHalted = $("#hud-halted");

const scenarioSelect = $("#scenarioSelect");
const btnReset = $("#btnReset");
const btnExport = $("#btnExport");
const btnFrame = $("#btnFrame");
const btnStep = $("#btnStep");
const btnPlay = $("#btnPlay");
const btnStop = $("#btnStop");
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
const deckPile = $("#deckPile");
const logLines = $("#logLines");
const handZone = $("#handZone");

let ws = null;

let currentSnapshot = null;
let currentFrame = null;
let utmRules = null;

let autoplayActive = false;
let autoplayTimer = null;

/**
 * Engine-specific rendering logic to handle different construction types.
 */
const EngineRenderers = {
    /**
     * The original (2,18) UTM implementation using Soul Snuffers and Infest.
     */
    rogozhin: {
        renderTape(snapshot, frame) {
            const tape = snapshot.tape || {};
            const head = snapshot.head ?? 0;
            const blankSymbol = "Cephalid";
            const radiusN = Number(radius.value);

            const lo = head - radiusN;
            const hi = head + radiusN;

            const logs = frame?.narration || [];
            let pulseType = null;
            let pulseTargetColor = null;

            if (logs.some(l => l.includes("Vigor"))) {
                pulseType = "plus";
                pulseTargetColor = logs.some(l => l.includes("white")) ? "white" : "green";
            } else if (logs.some(l => l.includes("Global Effect") || l.includes("Infest resolves"))) {
                pulseType = "minus";
                pulseTargetColor = "all";
            } else if (logs.some(l => l.includes("Dread of Night"))) {
                pulseType = "minus";
                pulseTargetColor = "black";
            }

            battlefieldRow.innerHTML = "";
            for (let pos = lo; pos <= hi; pos++) {
                const defaultColor = (pos < head) ? "green" : "white";
                const tok = tape[String(pos)] || {
                    creature_type: blankSymbol,
                    color: defaultColor,
                    tapped: false,
                    token_id: 0
                };
                const isHead = pos === head;
                const gainsAttached = (snapshot.illusory_gains_attached_to != null) && (tok.token_id === snapshot.illusory_gains_attached_to);

                const stackContainer = document.createElement("div");
                stackContainer.className = "card-stack";
                if (tok.tapped) stackContainer.classList.add("tapped");

                let flashClass = null;
                if (pulseType === "plus" && (pulseTargetColor === "all" || tok.color === pulseTargetColor)) {
                    flashClass = "pulse-plus";
                } else if (pulseType === "minus" && (pulseTargetColor === "all" || tok.color === pulseTargetColor)) {
                    flashClass = "pulse-minus";
                }

                const mainCard = tokenCard({pos, tok, isHead, blankSymbol, gainsAttached, flashClass});
                stackContainer.appendChild(mainCard);

                if (gainsAttached) {
                    stackContainer.appendChild(tokenCard({
                        pos,
                        tok: {creature_type: "Illusory Gains", color: "blue"},
                        isHead,
                        blankSymbol,
                        isAttachment: true
                    }));
                }
                battlefieldRow.appendChild(stackContainer);
            }
        },

        renderEngineRow(snapshot, frame) {
            bobPermanentsRow.innerHTML = "";
            const phasedOutList = (frame && frame.phased_out && frame.phased_out.length > 0)
                ? frame.phased_out
                : (snapshot.phased_out || []);

            const rootStyle = getComputedStyle(document.documentElement);
            const cardScale = parseFloat(rootStyle.getPropertyValue('--card-scale')) || 1;

            // Use Bob's battlefield data from the snapshot instead of hardcoded config
            const bobBattlefield = snapshot.bob_battlefield || [];

            // If no bob_battlefield data, fall back to empty array
            if (bobBattlefield.length === 0) {
                console.warn("No bob_battlefield data in snapshot");
                return;
            }

            // Map of cards that need state/tapped configuration
            const stateBasedCards = {
                "Rotlung Reanimator": [
                    {state: "q1", tapped: false},
                    {state: "q2", tapped: false}
                ],
                "Xathrid Necromancer": [
                    {state: "q1", tapped: true},
                    {state: "q2", tapped: true}
                ]
            };

            // Track which cards we've already rendered (to avoid duplicates)
            const renderedStates = new Set();

            bobBattlefield.forEach(cardName => {
                if (stateBasedCards[cardName]) {
                    // For reanimators, create state-based stacks
                    stateBasedCards[cardName].forEach(config => {
                        const key = `${cardName}-${config.state}-${config.tapped}`;
                        if (!renderedStates.has(key)) {
                            renderedStates.add(key);
                            const stackContainer = createInteractiveStack(
                                {name: cardName, state: config.state, tapped: config.tapped},
                                phasedOutList,
                                cardScale
                            );
                            bobPermanentsRow.appendChild(stackContainer);
                        }
                    });
                } else {
                    // For regular permanents, create a single card
                    const stackContainer = createInteractiveStack(
                        {name: cardName, count: 1},
                        phasedOutList,
                        cardScale
                    );
                    bobPermanentsRow.appendChild(stackContainer);
                }
            });
        }
    },

    /**
     * The 2024 Gadget-based construction using Choice Gadgets and Player Control.
     */
    gadget: {
        renderTape(snapshot, frame) {
            battlefieldRow.innerHTML = "";
            const tape = snapshot.tape || {};
            const extra = snapshot.extra || {};
            const controllers = extra.controllers || {};
            const head = snapshot.head;

            Object.entries(tape).forEach(([pos, tok]) => {
                const isHead = String(pos) === String(head);
                const controller = controllers[tok.token_id] || "Alice";
                const gainsAttached = (snapshot.illusory_gains_attached_to != null) && (tok.token_id === snapshot.illusory_gains_attached_to);

                const stackContainer = document.createElement("div");
                stackContainer.className = "card-stack";
                if (tok.tapped) stackContainer.classList.add("tapped");

                const card = tokenCard({
                    pos,
                    tok,
                    isHead,
                    controller,
                    blankSymbol: "Aetherborn",
                    gainsAttached
                });
                stackContainer.appendChild(card);

                // Add Illusory Gains attachment if needed
                if (gainsAttached) {
                    stackContainer.appendChild(tokenCard({
                        pos,
                        tok: {creature_type: "Illusory Gains", color: "blue"},
                        isHead,
                        controller,
                        blankSymbol: "Aetherborn",
                        isAttachment: true
                    }));
                }

                battlefieldRow.appendChild(stackContainer);
            });
        },

        renderEngineRow(snapshot, frame) {
            bobPermanentsRow.innerHTML = "";
            const bobBattlefield = snapshot.bob_battlefield || [];
            const rootStyle = getComputedStyle(document.documentElement);
            const cardScale = parseFloat(rootStyle.getPropertyValue('--card-scale')) || 1;

            bobBattlefield.forEach(cardName => {
                const stackContainer = createInteractiveStack(
                    {name: cardName, count: 1},
                    [],
                    cardScale
                );
                bobPermanentsRow.appendChild(stackContainer);
            });
        }
    }
};

/**
 * Helper for Rogozhin interactive engine stacks.
 */
function createInteractiveStack(config, phasedOutList, cardScale) {
    const stackContainer = document.createElement("div");
    stackContainer.className = "card-stack";
    stackContainer.style.marginRight = "-20px";

    let currentIndex = 0;

    function updateStackFront(container, frontIndex) {
        const cards = Array.from(container.querySelectorAll(".card:not(.attached)"));
        cards.forEach((card, idx) => {
            if (idx === frontIndex) {
                card.classList.add("stack-front");
                card.style.pointerEvents = "auto";
            } else {
                card.classList.remove("stack-front", "stack-hovered");
                card.style.pointerEvents = "none";
            }
        });
    }

    stackContainer.addEventListener("wheel", (e) => {
        const cards = Array.from(stackContainer.querySelectorAll(".card:not(.attached)"));
        if (cards.length <= 1) return;
        e.preventDefault();
        currentIndex = (e.deltaY > 0) ? currentIndex + 1 : currentIndex - 1;
        if (currentIndex < 0) currentIndex = cards.length - 1;
        if (currentIndex >= cards.length) currentIndex = 0;
        const maxOffset = cards.length - 1;
        cards.forEach((card, idx) => {
            const visualOffset = (idx - currentIndex + cards.length) % cards.length;
            card.style.zIndex = (cards.length - visualOffset) * 10;
            card.style.top = `${(maxOffset - visualOffset) * 4 * cardScale}px`;
            card.style.left = `${(maxOffset - visualOffset) * 2 * cardScale}px`;
        });
        updateStackFront(stackContainer, currentIndex);
    }, {passive: false});

    stackContainer.addEventListener("mouseover", (e) => {
        const hoveredCard = e.target.closest(".card");
        const cards = Array.from(stackContainer.querySelectorAll(".card:not(.attached)"));
        if (hoveredCard && hoveredCard.classList.contains("attached")) {
            cards.forEach(c => c.classList.remove("stack-hovered"));
            return;
        }
        if (cards[currentIndex]) cards[currentIndex].classList.add("stack-hovered");
    });

    stackContainer.addEventListener("mouseleave", () => {
        const cards = Array.from(stackContainer.querySelectorAll(".card:not(.attached)"));
        cards.forEach(c => c.classList.remove("stack-hovered"));
    });

    let stackTransitions = [];
    if (utmRules && config.state) {
        stackTransitions = Object.entries(utmRules[config.state])
            .map(([readType, t]) => ({...t, read_type: readType}))
            .filter(t => !!t.tapped === !!config.tapped);
    }

    const count = config.count ?? stackTransitions.length;
    for (let i = 0; i < count; i++) {
        const isBottom = (i === 0);
        const isPhasedOut = config.state && phasedOutList.includes(config.state);
        const cardEl = tokenCard({
            pos: "Engine",
            tok: {creature_type: config.name, color: "white", tapped: false},
            transition: stackTransitions[i] || null
        });
        if (isPhasedOut) cardEl.classList.add("phased-out");
        cardEl.style.position = "absolute";
        cardEl.style.top = `${(count - 1 - i) * 4 * cardScale}px`;
        cardEl.style.left = `${(count - 1 - i) * 2 * cardScale}px`;
        cardEl.style.zIndex = (count - i) * 10;
        stackContainer.appendChild(cardEl);

        if (isBottom && (config.name.includes("Rotlung") || config.name.includes("Xathrid"))) {
            const cloakEl = tokenCard({
                pos: "Engine",
                tok: {creature_type: "Cloak of Invisibility", color: "blue", tapped: false},
                isAttachment: true
            });
            cloakEl.style.zIndex = 0;
            stackContainer.appendChild(cloakEl);
        }
    }
    updateStackFront(stackContainer, 0);
    return stackContainer;
}

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
    autoplayActive = false;
    btnPlay.disabled = false;
    btnStop.disabled = true;
}

function stopAutoplayBecauseHalted() {
    if (!autoplayActive) return;
    clearAutoplay();

    const div = document.createElement("div");
    div.textContent = "AUTOPLAY stopped: machine is halted.";
    div.style.color = "rgba(224,193,90,0.95)";
    logLines.prepend(div);
}

function startAutoplay() {
    if (currentSnapshot && currentSnapshot.halted) return;
    clearAutoplay();
    autoplayActive = true;
    btnPlay.disabled = true;
    btnStop.disabled = false;
    autoplayNext();
}

function autoplayNext() {
    if (!autoplayActive || (currentSnapshot && currentSnapshot.halted)) {
        clearAutoplay();
        return;
    }

    const sliderVal = Number(speed.value);
    // Linear mapping: 0 -> 1200ms, 100 -> 0ms
    const delay = (100 - sliderVal) * 2;

    autoplayTimer = setTimeout(() => {
        // If speed is very high, request a full step instead of a single frame
        if (sliderVal > 99) {
            send({type: "step_step"});
        } else {
            send({type: "step_frame"});
        }
    }, delay);
}

// Update the message listener to chain the next autoplay frame

function updateHud(snapshot) {
    hudStep.textContent = `STEP: ${snapshot?.step_index ?? "-"}`;
    hudState.textContent = `STATE: ${snapshot?.state ?? "-"}`;
    hudHead.textContent = `HEAD: ${snapshot?.head ?? "-"}`;
    hudHalted.textContent = `HALTED: ${snapshot?.halted ?? "-"}`;
    hudHalted.style.color = snapshot?.halted ? "rgba(255,89,100,0.95)" : "rgba(231,238,247,0.7)";
}

function tokenCard({
                       pos,
                       tok,
                       controller, // Added for 2024 construction
                       isHead,
                       blankSymbol,
                       gainsAttached,
                       flashClass,
                       isAttachment = false,
                       transition = null
                   }) {
    const el = document.createElement("div");
    el.className = "card";

    // Visual indicators for control
    if (controller === "Alice") el.classList.add("controlled-alice");
    if (controller === "Bob") el.classList.add("controlled-bob");
    if (controller === "Charlie") el.classList.add("controlled-charlie");

    // Add a controller badge to the card UI
    if (controller) {
        const badge = document.createElement("div");
        badge.className = "control-badge";
        badge.textContent = controller[0]; // 'A', 'B', etc.
        el.appendChild(badge);
    }
    if (isAttachment) el.classList.add("attached");

    const creatureType = tok?.creature_type ?? (isAttachment ? "Illusory Gains" : blankSymbol);

    // VISUAL TWEAK: If this is an implicit Cephalid at the head position during
    // the "read/die" phase, make it invisible to show an empty slot.
    if (!isAttachment && creatureType === "Cephalid" && isHead) {
        const tokenId = tok?.token_id ?? 0;

        // Hide only when the slot is genuinely empty (no real token written yet)
        // AND the current frame is the death SBA or the reanimator trigger.
        // We identify this window by: read_pos points at the head AND written_pos is not yet set.
        const headJustDied =
            tokenId === 0 &&
            currentFrame?.read_pos === pos &&
            currentFrame?.written_pos == null;

        const awaitingWrite =
            tokenId === 0 &&
            currentFrame?.read_pos == null &&
            currentFrame?.written_pos == null &&
            currentFrame?.read_type != null; // read_type lingers on the TRIGGER frame

        if (headJustDied || awaitingWrite) {
            el.style.opacity = "0";
            el.style.pointerEvents = "none";
        }
    }

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
        nameLower.includes("steely resolve") ||
        nameLower.includes("prismatic omen") ||
        nameLower.includes("recycle")) {
        color = "green";
    } else if (nameLower.includes("coalition victory") ||
        nameLower.includes("ancient tomb")) {
        color = "gold";
    } else if (nameLower.includes("wheel of sun and moon") ||
        nameLower.includes("privileged position")) {
        color = "green/white";
    } else if (nameLower.includes("rotlung reanimator") ||
        nameLower.includes("xathrid necromancer")) {
        color = "black/green/white";
    } else if (nameLower.includes("vigor") ||
        nameLower.includes("blazing archon")) {
        color = "white/black/red/green";
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
    if (color === "white/black/red/green") el.classList.add("color-white-black-red-green");
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
    } else if (nameLower.includes("wild evocation") || nameLower.includes("dread of night") || nameLower.includes("steely resolve") || nameLower.includes("prismatic omen") || nameLower.includes("choke") || nameLower.includes("recycle") || nameLower.includes("privileged position")) {
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
        typeLine.textContent = "Creature - Assembly-Worker";
    } else if (nameLower.includes("blazing archon")) {
        typeLine.textContent = "Creature - Assembly-Worker";
    } else {
        typeLine.textContent = `Token Creature - ${creatureType}`;
    }

// Specific override for non-token named creatures


// Text Box
    const textBox = document.createElement("div");
    textBox.className = "text-box";

    const parseSymbols = (text) => {
        return text
            .replace(/{T}/g, '<span class="ms ms-tap">T</span>')
            .replace(/{C}/g, '<span class="ms ms-c">C</span>');
    };

    if (nameLower.includes("cloak of invisibility")) {
        textBox.innerHTML = "Enchanted creature has phasing. <i>(It exists only every other turn.)</i><br><br>Enchanted creature can't be blocked except by Walls.";
    } else if (nameLower.includes("illusory gains")) {
        textBox.innerHTML = "You control enchanted creature.<br><br>Whenever a creature enters the battlefield under an opponent's control, attach Illusory Gains to that creature.";
    } else if (nameLower.includes("rotlung reanimator") || nameLower.includes("xathrid necromancer")) {
        const isRotlung = nameLower.includes("rotlung");

        // Priority 1: Specific transition passed in (for engine row)
        // Priority 2: Current frame's transition (for stack/battlefield triggers)
        let rule = transition;
        if (!rule && (currentFrame?.read_type || currentFrame?.written_type)) {
            // If it's a trigger on the stack, it represents the transition being executed
            const state = currentFrame.state_from || currentSnapshot?.state || "q1";
            const readType = currentFrame.read_type || currentFrame.written_type; // Fallback for various phases
            rule = utmRules?.[state]?.[readType];
            if (rule && !rule.read_type) rule.read_type = readType;
        }

        if (rule) {
            const readType = rule.read_type || "another creature";
            const writeType = rule.write_type;
            const color = rule.move_color;
            const tapped = rule.tapped ? " tapped" : "";

            textBox.innerHTML = `Whenever ${isRotlung ? "Rotlung Reanimator" : "Xathrid Necromancer"} or another ${readType} dies, create a${tapped} ${color} ${writeType} creature token.`;
        } else {
            const triggerType = isRotlung ? "Zombie" : "Human";
            textBox.innerHTML = `Whenever ${isRotlung ? "Rotlung Reanimator" : "Xathrid Necromancer"} or another ${triggerType} dies, create a 2/2 black Zombie creature token.`;
        }
    } else if (nameLower.includes("infest")) {
        textBox.innerHTML = "All creatures get -2/-2 until end of turn.";
    } else if (nameLower.includes("cleansing beam")) {
        textBox.innerHTML = "Cleansing Beam deals 2 damage to target creature and each other creature that shares a color with it.";
    } else if (nameLower.includes("coalition victory")) {
        textBox.innerHTML = "You win the game if you control a land of each basic land type and a creature of each color.";
    } else if (nameLower.includes("soul snuffers")) {
        textBox.innerHTML = "When this creature enters, put a -1/-1 counter on each creature.";
    } else if (nameLower.includes("wild evocation")) {
        textBox.innerHTML = "At the beginning of each player's upkeep, that player reveals a card at random from their hand. If it's a land card, the player puts it onto the battlefield. Otherwise, the player casts it without paying its mana cost if able.";
    } else if (nameLower.includes("dread of night")) {
        textBox.innerHTML = "Black creatures get -1/-1.";
    } else if (nameLower.includes("steely resolve")) {
        textBox.innerHTML = "As this enchantment enters, choose a creature type. Creatures of the chosen type have shroud. <i>(Assembly-Worker)</i>";
    } else if (nameLower.includes("vigor")) {
        textBox.innerHTML = "Trample.<br>If damage would be dealt to another creature you control, prevent that damage.<br>Put a +1/+1 counter on that creature for each 1 damage prevented this way.<br>When Vigor is put into a graveyard from anywhere, shuffle it into its owner’s library.";
    } else if (nameLower.includes("mesmeric orb")) {
        textBox.innerHTML = "Whenever a permanent becomes untapped, its controller mills a card.";
    } else if (nameLower.includes("ancient tomb")) {
        textBox.innerHTML = parseSymbols("{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.");
    } else if (nameLower.includes("prismatic omen")) {
        textBox.innerHTML = "Lands you control are every basic land type in addition to their other types.";
    } else if (nameLower.includes("choke")) {
        textBox.innerHTML = "Islands don't untap during their controllers' untap steps.";
    } else if (nameLower.includes("blazing archon")) {
        textBox.innerHTML = "Creatures can't attack you.";
    } else if (nameLower.includes("wheel of sun and moon")) {
        textBox.innerHTML = "Enchant player.<br>If a card would be put into enchanted player's graveyard from anywhere, instead that card is revealed and put on the bottom of its owner's library.";
    } else if (nameLower.includes("recycle")) {
        textBox.innerHTML = "Skip your draw step.<br>Whenever you play a card, draw a card.<br>Your maximum hand size is two.";
    } else if (nameLower.includes("privileged position")) {
        textBox.innerHTML = "Other permanents you control have hexproof.";
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

        let p = 2;
        let t = 2;
        const typeLower = creatureType.toLowerCase();
        const phase = currentFrame?.phase || "";
        const location = pos; // "Hand", "Deck", "Alice's Board", or a number (tape)

        if (typeLower.includes("soul snuffers")) {
            // Soul Snuffers is base 3/3
            if (location === "Hand" || location === "Deck" || phase.includes("CAST")) {
                p = 3;
                t = 3;
            } else if (phase.includes("RESOLVE")) {
                // Just resolved, hasn't processed ETB or Dread of Night yet
                p = 3;
                t = 3;
            } else if (phase.includes("SBA")) {
                const logs = currentFrame?.narration || [];
                const isGlobalEffectFrame = logs.some(l => l.includes("Global Effect"));
                const isDeathFrame = logs.some(l => l.includes("Dread of Night"));

                if (isDeathFrame) {
                    p = 0;
                    t = 0; // Final SBA frame: dies to Dread of Night
                } else if (isGlobalEffectFrame) {
                    p = 2;
                    t = 2; // First SBA frame: applied its own -1/-1 counter
                } else {
                    p = 1;
                    t = 1; // Default battlefield state if caught between frames
                }
            } else {
                p = 1;
                t = 1;
            }
        } else if (typeLower.includes("blazing archon") || typeLower.includes("vigor")) {

            p = 6;
            t = 6;
        } else if (tok) {
            // Use power/toughness from server (base + distance + global offsets + infest)
            // then apply counters (plus/minus)
            const baseP = tok.power || 0;
            const baseT = tok.toughness || 0;
            const plus = tok.plus1_counters || 0;
            const minus = tok.minus1_counters || 0;

            p = Math.max(0, baseP + plus - minus);
            t = Math.max(0, baseT + plus - minus);
        }

        if (typeLower.includes("blazing archon") || typeLower.includes("vigor") || typeLower.includes("rotlung") || typeLower.includes("xathrid")) {
            ptBox.textContent = `*/*`;
            frame.appendChild(ptBox);
        } else {
            ptBox.textContent = `${p}/${t}`;
            frame.appendChild(ptBox);
        }
    }

    el.appendChild(frame);
    el.title = isAttachment ? "Illusory Gains" : `Position ${pos}\nType: ${creatureType}\nToken: #${tokenId}`;

    return el;
}

function render(snapshot, frame, graveyardData = [], stackData = []) {
    if (!snapshot) return;

    updateHud(snapshot);
    renderDeck(snapshot.deck || []);

    const engine = snapshot.engine_name || "rogozhin";
    const renderer = EngineRenderers[engine] || EngineRenderers.rogozhin;

    renderer.renderEngineRow(snapshot, frame);
    renderer.renderTape(snapshot, frame);

    // --- Alice Battlefield ---
    if (aliceBattlefieldRow) {
        aliceBattlefieldRow.innerHTML = "";
        // Look for battlefield data in the snapshot payload
        const aliceCards = snapshot.alice_battlefield || [];

        // Determine pulse type from frame narration (needed for Soul Snuffers animation)
        const logs = frame?.narration || [];
        let pulseType = null;
        let pulseTargetColor = null;

        if (logs.some(l => l.includes("Vigor"))) {
            pulseType = "plus";
            pulseTargetColor = logs.some(l => l.includes("white")) ? "white" : "green";
        } else if (logs.some(l => l.includes("Global Effect") || l.includes("Infest resolves"))) {
            pulseType = "minus";
            pulseTargetColor = "all";
        } else if (logs.some(l => l.includes("Dread of Night"))) {
            pulseType = "minus";
            pulseTargetColor = "black";
        }

        // Tracking for stacking duplicate cards
        const counts = {};

        aliceCards.forEach((cardName) => {
            counts[cardName] = (counts[cardName] || 0) + 1;
            const index = counts[cardName] - 1;
            const isAncientTomb = cardName === "Ancient Tomb";

            const stackContainer = document.createElement("div");
            stackContainer.className = "card-stack";
            if (isAncientTomb) stackContainer.classList.add("tapped");

            // Check if this card should pulse
            let aliceFlashClass = null;
            // Soul Snuffers is Black, Dread of Night affects Black.
            // Since pulseTargetColor is "all" for these effects, any creature pulses.
            if (cardName == "Soul Snuffers" && pulseType === "minus") {
                aliceFlashClass = "pulse-minus";
            }

            const cardEl = tokenCard({
                pos: "Alice's Board",
                tok: {creature_type: cardName, color: "white", tapped: isAncientTomb},
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false,
                flashClass: aliceFlashClass // Apply the pulse here
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
        const rootStyle = getComputedStyle(document.documentElement);
        const cardScale = parseFloat(rootStyle.getPropertyValue('--card-scale')) || 1;

        for (let i = 0; i < stack.length; i++) {
            const isTop = (i === stack.length - 1);
            const stackItemName = stack[i];
            const stackItemLower = stackItemName.toLowerCase();

            // Build transition for Rotlung/Xathrid on the stack
            let stackTransition = null;
            if (stackItemLower.includes("rotlung") || stackItemLower.includes("xathrid")) {
                const state = frame?.state_from || currentSnapshot?.state || "q1";
                const readType = frame?.read_type;
                if (utmRules && readType && utmRules[state] && utmRules[state][readType]) {
                    stackTransition = {...utmRules[state][readType], read_type: readType};
                }
            }

            const spellEl = tokenCard({
                pos: "",
                tok: {creature_type: stackItemName, color: "white"},
                isHead: false,
                blankSymbol: "Cephalid",
                gainsAttached: false,
                isAttachment: false,
                transition: stackTransition
            });

            spellEl.classList.add("stack-item");

            if (!isTop) {
                spellEl.classList.add("stack-item-below");
                // Stagger every item behind the one above it
                const offset = (stack.length - 2 - i) * 30 * cardScale;
                spellEl.style.top = `${offset}px`;
                spellEl.style.zIndex = i;
            } else {
                const offset = (stack.length - 1) * 30 * cardScale;
                spellEl.style.zIndex = stack.length + 1;
                spellEl.style.top = `${offset}px`;
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
        // Reverse the narration array if we're prepending,
        // so the earliest event in the batch ends up at the bottom of the new block
        const logs = [...frame.narration];
        for (const s of logs) {
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

function renderDeck(deck) {
    if (!deckPile) return;
    deckPile.innerHTML = "";
    const count = deck.length;
    if (count === 0) {
        deckPile.innerHTML = `<div style="color: rgba(231,238,247,0.3); font-size: 10px;">(empty)</div>`;
        return;
    }

    const visualCount = Math.min(count, 10);
    const containerWidth = deckPile.clientWidth || 300;
    const containerHeight = deckPile.clientHeight || 240;

    for (let i = 0; i < visualCount; i++) {
        const cardName = deck[i] || "Unknown Card";

        const flipContainer = document.createElement("div");
        flipContainer.className = "deck-card-container";
        if (i === 0) flipContainer.classList.add("next-draw");

        const centerX = (containerWidth / 2) - 75;
        const centerY = (containerHeight / 2) - 105;

        // Natural stack: top card (i=0) has the highest z-index
        flipContainer.style.left = `${centerX + (i * 2)}px`;
        flipContainer.style.top = `${centerY - (i * 2)}px`;
        flipContainer.style.zIndex = visualCount - i;
        flipContainer.style.setProperty('--index', i);

        const flipper = document.createElement("div");
        flipper.className = "deck-card-flipper";

        // Front side (High quality card)
        const front = tokenCard({
            pos: "Deck",
            tok: {creature_type: cardName, color: "white"},
            isHead: false,
            blankSymbol: "Cephalid",
            gainsAttached: false
        });
        front.classList.add("deck-card-front");

        if (i === 0) {
            const ribbon = document.createElement("div");
            ribbon.className = "next-draw-ribbon";
            ribbon.textContent = "NEXT DRAW";
            front.appendChild(ribbon);
        }

        // Back side
        const back = document.createElement("div");
        back.className = "card-back deck-card-back";

        flipper.appendChild(front);
        flipper.appendChild(back);
        flipContainer.appendChild(flipper);
        deckPile.appendChild(flipContainer);
    }

    const label = document.createElement("div");
    label.style.position = "absolute";
    label.style.bottom = "5px";
    label.style.width = "100%";
    label.style.textAlign = "center";
    label.style.fontSize = "10px";
    label.style.fontWeight = "bold";
    label.style.color = "var(--gold)";
    label.textContent = `${count} CARDS`;
    label.style.zIndex = 20;
    deckPile.appendChild(label);
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
            if (msg.utm_rules) utmRules = msg.utm_rules;
            render(currentSnapshot, currentFrame, msg.graveyard, msg.stack); // Pass stack

            if (currentSnapshot?.halted) {
                stopAutoplayBecauseHalted();
            } else if (autoplayActive) {
                autoplayNext(); // Continue autoplay after a full step
            }
            return;
        }

        if (msg.type === "frame") {
            currentFrame = msg.frame;
            currentSnapshot = msg.snapshot;
            render(currentSnapshot, currentFrame, msg.graveyard, msg.stack);

            if (currentSnapshot?.halted) {
                stopAutoplayBecauseHalted();
            } else if (autoplayActive) {
                autoplayNext(); // Chain the next frame
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
    logLines.innerHTML = "";
});

btnExport.addEventListener("click", () => {
    if (!currentSnapshot) return;

    // 1. Get and sort entries
    const entries = Object.entries(currentSnapshot.tape || {})
        .filter(([_, tok]) => tok && tok.token_id !== 0);

    entries.sort(([posA], [posB]) => {
        const isIntA = /^-?\d+$/.test(posA);
        const isIntB = /^-?\d+$/.test(posB);
        if (isIntA && isIntB) return parseInt(posA, 10) - parseInt(posB, 10);
        if (isIntA !== isIntB) return isIntA ? -1 : 1;
        return String(posA).localeCompare(String(posB), undefined, {numeric: true});
    });

    // 2. Manually construct the JSON string to preserve key order
    const tapeLines = entries.map(([pos, tok]) => {
        const tokenJson = JSON.stringify({
            creature_type: tok.creature_type,
            token_id: tok.token_id
        }, null, 4).replace(/\n/g, '\n    ');
        return `    "${pos}": ${tokenJson}`;
    });

    const exportObj = {
        name: `Exported ${currentSnapshot.engine_name || 'machine'}`,
        engine: currentSnapshot.engine_name || "rogozhin",
        state: currentSnapshot.state,
        head: currentSnapshot.head
    };

    let jsonString = "{\n";
    jsonString += `  "name": ${JSON.stringify(exportObj.name)},\n`;
    jsonString += `  "engine": ${JSON.stringify(exportObj.engine)},\n`;
    jsonString += `  "state": ${JSON.stringify(exportObj.state)},\n`;
    jsonString += `  "head": ${JSON.stringify(exportObj.head)},\n`;
    jsonString += `  "tape": {\n${tapeLines.join(",\n")}\n  }`;

    if (currentSnapshot.extra && currentSnapshot.extra.controllers) {
        jsonString += ",\n" + `  "controllers": ${JSON.stringify(currentSnapshot.extra.controllers, null, 2).replace(/\n/g, '\n  ')}`;
    }
    jsonString += "\n}";

    const blob = new Blob([jsonString], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tape_export_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

btnFrame.addEventListener("click", () => send({type: "step_frame"}));
btnStep.addEventListener("click", () => send({type: "step_step"}));

scenarioSelect.addEventListener("change", () => {
    send({type: "load_scenario", name: scenarioSelect.value});
    graveyardList.innerHTML = "";
    logLines.innerHTML = "";
});

btnPlay.addEventListener("click", () => startAutoplay());
btnStop.addEventListener("click", () => clearAutoplay());

speed.addEventListener("input", () => {
    if (autoplayActive) startAutoplay();
});

radius.addEventListener("input", () => {
    render(currentSnapshot, currentFrame);
});

// Start
connect();