/**
 * Invoice Form JavaScript
 * Handles dynamic form operations, calculations, and validations
 */

let reservationCount = 1;
let paymentCount = 1;

const TRASH_ICON = `<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>`;
const DRAG_ICON  = `<svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor"><circle cx="3" cy="3" r="1.5"/><circle cx="7" cy="3" r="1.5"/><circle cx="3" cy="8" r="1.5"/><circle cx="7" cy="8" r="1.5"/><circle cx="3" cy="13" r="1.5"/><circle cx="7" cy="13" r="1.5"/></svg>`;

/**
 * Update payment reservation dropdowns with current reservation numbers
 */
function updatePaymentReservationDropdowns() {
    const reservationInputs = document.querySelectorAll('input[name="reservation_number"]');
    let resOptions = '<option value="">Res#</option>';
    
    reservationInputs.forEach(input => {
        if (input.value && input.value.trim()) {
            const val = input.value.trim();
            resOptions += `<option value="${val}">${val}</option>`;
        }
    });
    
    const paymentSelects = document.querySelectorAll('select[name="payment_reservation_no"]');
    paymentSelects.forEach(select => {
        const currentValue = select.value;
        select.innerHTML = resOptions;
        if (currentValue) {
            select.value = currentValue;
        }
    });
}

/**
 * Format number with thousand separators
 */
function formatNumber(n) {
    try {
        return Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    } catch (e) {
        return n;
    }
}

/**
 * Parse string to number safely
 */
function parseNumber(val) {
    if (!val && val !== 0) return 0;
    const v = Number(val);
    return isNaN(v) ? 0 : v;
}

/**
 * Recalculate totals and remaining balance
 */
function recalculate() {
    // Calculate total reservations
    const resTotals = Array.from(document.querySelectorAll('input[name="reservation_total"]'))
        .map(i => parseNumber(i.value));
    const totalRes = resTotals.reduce((a, b) => a + b, 0);

    // Calculate total payments (convert to SAR)
    const payments = Array.from(document.querySelectorAll('.payment-item'));
    let totalPaidSar = 0;
    
    payments.forEach(p => {
        const amtEl = p.querySelector('input[name="payment_amount"]');
        const curEl = p.querySelector('select[name="payment_currency"]');
        const exEl = p.querySelector('input[name="payment_exchange"]');
        const amount = parseNumber(amtEl ? amtEl.value : 0);
        const cur = curEl ? curEl.value : 'SAR';
        const ex = parseNumber(exEl ? exEl.value : 1) || 1;

        let amountSar = 0;
        if (cur === 'SAR') {
            amountSar = amount;
        } else if (cur === 'IDR') {
            amountSar = ex !== 0 ? amount / ex : 0;
        } else { // USD or others
            amountSar = amount * ex;
        }
        totalPaidSar += amountSar;
    });

    const remaining = totalRes - totalPaidSar;

    // Update UI
    document.getElementById('total-reservations').textContent = formatNumber(totalRes) + ' SAR';
    document.getElementById('total-payments').textContent = formatNumber(Math.round(totalPaidSar)) + ' SAR';
    
    const remainingEl = document.getElementById('remaining-balance');
    remainingEl.textContent = formatNumber(Math.round(remaining)) + ' SAR';
    
    // Color code remaining balance
    if (remaining <= 0) {
        remainingEl.className = 'val green';
    } else if (remaining < totalRes) {
        remainingEl.className = 'val yellow';
    } else {
        remainingEl.className = 'val red';
    }
}

/**
 * Add new reservation row
 */
function addReservation() {
    reservationCount++;
    const container = document.getElementById('reservations');
    const div = document.createElement('div');
    div.className = 'item';
    div.innerHTML = `
        <input class="compact-res-no" aria-label="Reservation Number" type="text" name="reservation_number" placeholder="0001" required inputmode="numeric" oninput="updatePaymentReservationDropdowns()">
        <input class="compact-hotel" aria-label="Hotel Name" type="text" name="hotel" placeholder="Hotel Name">
        <input aria-label="Check In" type="date" name="check_in" placeholder="Check In">
        <input aria-label="Check Out" type="date" name="check_out" placeholder="Check Out">
        <input aria-label="Reservation Total" type="number" name="reservation_total" placeholder="Total SAR" step="0.01" required oninput="recalculate()">
        <button type="button" class="btn-remove" onclick="this.closest('.item').remove(); recalculate(); updatePaymentReservationDropdowns();">${TRASH_ICON}</button>
    `;
    container.appendChild(div);
    bindCheckInOut(div);
    const first = div.querySelector('input[name="reservation_number"]');
    if (first) first.focus();
}

/**
 * Add new payment row
 */
function addPayment() {
    paymentCount++;
    const container = document.getElementById('payments');
    const div = document.createElement('div');
    div.className = 'payment-item';
    div.innerHTML = `
        <div class="drag-handle" draggable="true">${DRAG_ICON}</div>
        <select aria-label="Reservation Number" name="payment_reservation_no" required>
            <option value="">Res#</option>
        </select>
        <input aria-label="Payment Date" type="date" name="payment_date" required onchange="recalculate()">
        <input class="compact-method" aria-label="Payment Method" type="text" name="payment_method" placeholder="Method" required>
        <input aria-label="Payment Amount" type="number" step="0.01" name="payment_amount" placeholder="Amount" required oninput="recalculate()">
        <select aria-label="Payment Currency" name="payment_currency" onchange="toggleExchange(this); recalculate()">
            <option value="SAR">SAR</option>
            <option value="USD">USD</option>
            <option value="IDR">IDR</option>
        </select>
        <input aria-label="Exchange Rate" type="number" step="0.0001" name="payment_exchange" placeholder="Rate" value="1" readonly oninput="recalculate()">
        <textarea aria-label="Payment Note" name="payment_note" placeholder="Note (optional)"></textarea>
        <div class="proof-cell">
          <label class="proof-btn" title="Upload bukti">
            <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
            <input type="file" class="payment-proof-input" accept="image/*,.pdf" style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;" onchange="showProofName(this)">
          </label>
          <span class="proof-fname"></span>
        </div>
        <button type="button" class="btn-remove" onclick="this.closest('.payment-item').remove(); recalculate();">${TRASH_ICON}</button>
    `;
    container.appendChild(div);
    updatePaymentReservationDropdowns();
    
    // Focus first input for convenience
    const first = div.querySelector('input[name="payment_date"]');
    if (first) first.focus();
}

function showProofName(input) {
    var fname = input.files[0] ? input.files[0].name : '';
    var span = input.closest('.proof-cell').querySelector('.proof-fname');
    if (span) span.textContent = fname;
}

/**
 * Toggle exchange rate field based on currency selection
 */
function toggleExchange(sel) {
    const exchange = sel.parentNode.querySelector('input[name="payment_exchange"]');
    if (!exchange) return;
    
    if (sel.value === 'SAR') {
        exchange.readOnly = true;
        exchange.value = '1';
    } else {
        exchange.readOnly = false;
        if (!exchange.value || exchange.value === '1') {
            exchange.value = '';
        }
    }
}


/**
 * Drag-to-reorder for payment rows
 */
function initDragSort() {
    const container = document.getElementById('payments');
    let dragSrc = null;

    function clearDropClasses() {
        container.querySelectorAll('.payment-item').forEach(function(el) {
            el.classList.remove('drop-above', 'drop-below');
        });
    }

    container.addEventListener('dragstart', function(e) {
        const handle = e.target.closest('.drag-handle');
        if (!handle) return;
        dragSrc = handle.closest('.payment-item');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setDragImage(dragSrc, 0, 20);
        setTimeout(function() { dragSrc.classList.add('is-dragging'); }, 0);
    });

    container.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        clearDropClasses();
        const target = e.target.closest('.payment-item');
        if (!target || target === dragSrc) return;
        const rect = target.getBoundingClientRect();
        if (e.clientY < rect.top + rect.height / 2) {
            target.classList.add('drop-above');
        } else {
            target.classList.add('drop-below');
        }
    });

    container.addEventListener('dragleave', function(e) {
        if (!container.contains(e.relatedTarget)) clearDropClasses();
    });

    container.addEventListener('drop', function(e) {
        e.preventDefault();
        if (!dragSrc) return;
        const target = e.target.closest('.payment-item');
        if (!target || target === dragSrc) { cleanupDrag(); return; }
        const rect = target.getBoundingClientRect();
        if (e.clientY < rect.top + rect.height / 2) {
            container.insertBefore(dragSrc, target);
        } else {
            container.insertBefore(dragSrc, target.nextSibling);
        }
        cleanupDrag();
    });

    container.addEventListener('dragend', cleanupDrag);

    function cleanupDrag() {
        if (dragSrc) dragSrc.classList.remove('is-dragging');
        clearDropClasses();
        dragSrc = null;
    }
}

/**
 * Initialize on page load
 */
function bindCheckInOut(container) {
    const checkIn  = container.querySelector('input[name="check_in"]');
    const checkOut = container.querySelector('input[name="check_out"]');
    if (!checkIn || !checkOut) return;
    checkIn.addEventListener('change', function() {
        if (checkIn.value) checkOut.min = checkIn.value;
        if (checkOut.value && checkOut.value < checkIn.value) checkOut.value = '';
    });
}

window.addEventListener('load', function() {
    recalculate();
    updatePaymentReservationDropdowns();
    document.querySelectorAll('#reservations .item').forEach(bindCheckInOut);
    initDragSort();

    // Rename proof file inputs by row index before submit so backend can match by position
    var form = document.getElementById('invoice-form');
    if (form) {
        form.addEventListener('submit', function() {
            document.querySelectorAll('#payments .payment-item').forEach(function(row, i) {
                var f = row.querySelector('.payment-proof-input');
                if (f) f.name = 'payment_proof_' + i;
            });
        });
    }
});
