(() => {
    const body = document.body;
    const navToggle = document.querySelector("[data-nav-toggle]");
    const navScrim = document.querySelector("[data-nav-scrim]");

    function setNavigation(open) {
        body.classList.toggle("nav-open", open);
        navToggle?.setAttribute("aria-expanded", String(open));
    }

    navToggle?.addEventListener("click", () => setNavigation(!body.classList.contains("nav-open")));
    navScrim?.addEventListener("click", () => setNavigation(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setNavigation(false);
    });

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    const monitor = document.querySelector("[data-basket-monitor]");
    if (!monitor) return;

    const lineContainer = monitor.querySelector("[data-basket-lines]");
    const emptyState = monitor.querySelector("[data-basket-empty]");
    const ledgerWrap = monitor.querySelector("[data-ledger-wrap]");
    const countNode = monitor.querySelector("[data-basket-count]");
    const totalNode = monitor.querySelector("[data-basket-total]");
    const totalLabelNode = monitor.querySelector("[data-basket-total-label]");
    const statusNode = monitor.querySelector("[data-basket-status]");
    const updatedNode = monitor.querySelector("[data-basket-updated]");
    const liveState = monitor.querySelector("[data-live-state]");
    const money = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

    function cell(label, className = "") {
        const node = document.createElement("td");
        node.dataset.label = label;
        if (className) node.className = className;
        return node;
    }

    function renderLine(line) {
        const row = document.createElement("tr");
        const productCell = cell("Article");
        const product = document.createElement("span");
        product.className = "product-cell";
        const name = document.createElement("strong");
        name.textContent = line.product.name;
        const sku = document.createElement("small");
        sku.textContent = line.catalogued ? line.product.sku : `Label modèle : ${line.detected_label}`;
        product.append(name, sku);
        productCell.append(product);

        const price = cell("Prix unitaire", "price");
        price.textContent = line.catalogued ? `${money.format(Number(line.unit_price))} FC` : "À définir";
        const quantity = cell("Quantité");
        const quantityValue = document.createElement("span");
        quantityValue.className = "quantity-readonly";
        quantityValue.textContent = line.quantity;
        quantity.append(quantityValue);
        const subtotal = cell("Sous-total", "align-right price strong");
        subtotal.textContent = line.catalogued ? `${money.format(Number(line.subtotal))} FC` : "—";
        row.append(productCell, price, quantity, subtotal);
        return row;
    }

    function renderBasket(payload) {
        lineContainer.replaceChildren(...payload.lines.map(renderLine));
        const isEmpty = payload.lines.length === 0;
        emptyState.hidden = !isEmpty;
        ledgerWrap.classList.toggle("is-empty", isEmpty);
        countNode.textContent = payload.item_count;
        totalNode.textContent = `${money.format(Number(payload.total))} FC`;
        totalLabelNode.textContent = payload.uncatalogued_item_count
            ? "Total des articles répertoriés"
            : "Total du panier";
        statusNode.textContent = payload.status_label || payload.status;
        statusNode.className = `status-badge ${payload.status === "OPEN" ? "status-success" : "status-warning"}`;
        updatedNode.textContent = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(payload.updated_at));
    }

    async function refreshBasket() {
        try {
            const response = await fetch(monitor.dataset.sessionUrl, { headers: { Accept: "application/json" } });
            if (!response.ok) throw new Error("basket_unavailable");
            renderBasket(await response.json());
        } catch (_error) {
            liveState.textContent = "Actualisation impossible";
            liveState.className = "status-badge status-warning";
        }
    }

    let reconnectDelay = 1000;
    function connect() {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(`${protocol}://${window.location.host}${monitor.dataset.wsUrl}`);
        socket.addEventListener("open", () => {
            reconnectDelay = 1000;
            liveState.textContent = "En direct";
            liveState.className = "status-badge status-success";
        });
        socket.addEventListener("message", refreshBasket);
        socket.addEventListener("close", () => {
            liveState.textContent = "Reconnexion";
            liveState.className = "status-badge status-neutral";
            window.setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        });
        socket.addEventListener("error", () => socket.close());
    }

    connect();
})();

(() => {
    const notice = document.querySelector("[data-rfid-enrollment-notice]");
    if (!notice) return;

    const title = notice.querySelector("[data-rfid-notice-title]");
    const message = notice.querySelector("[data-rfid-notice-message]");
    const dismiss = notice.querySelector("[data-rfid-notice-dismiss]");
    const managePath = new URL(notice.dataset.manageUrl, window.location.origin).pathname;
    const isManagementPage = window.location.pathname === managePath;
    let pendingCount = Number(notice.dataset.pendingCount || "0");

    function copyFor(count, eventType) {
        if (eventType === "rfid.enrollment.approved") {
            return ["Carte RFID enregistrée", "L'association a été enregistrée."];
        }
        if (eventType === "rfid.enrollment.rejected") {
            return ["Demande RFID refusée", "La carte ne peut pas démarrer d'achat."];
        }
        if (count === 1) {
            return ["Carte RFID à traiter", "Une carte inconnue attend votre validation."];
        }
        return ["Cartes RFID à traiter", `${count} cartes inconnues attendent votre validation.`];
    }

    function showNotice(eventType = "rfid.enrollment.requested") {
        const [nextTitle, nextMessage] = copyFor(pendingCount, eventType);
        title.textContent = nextTitle;
        message.textContent = nextMessage;
        notice.hidden = false;
    }

    function hideNotice() {
        notice.hidden = true;
    }

    dismiss?.addEventListener("click", hideNotice);
    if (pendingCount > 0 && !isManagementPage) showNotice();

    let reconnectDelay = 1000;
    function connect() {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(`${protocol}://${window.location.host}/ws/v1/rfid-enrollments/`);
        socket.addEventListener("open", () => { reconnectDelay = 1000; });
        socket.addEventListener("message", (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch (_error) {
                return;
            }
            if (!payload || !String(payload.type || "").startsWith("rfid.enrollment.")) return;
            pendingCount = Number(payload.pending_count || "0");
            if (pendingCount > 0 || payload.type !== "rfid.enrollment.approved") {
                showNotice(payload.type);
            } else {
                hideNotice();
            }
        });
        socket.addEventListener("close", () => {
            window.setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        });
        socket.addEventListener("error", () => socket.close());
    }

    connect();
})();
