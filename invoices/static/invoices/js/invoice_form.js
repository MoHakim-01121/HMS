/**
 * Invoice Form JavaScript
 * Handles dynamic form operations, calculations, and validations
 */

let reservationCount = 1;
let paymentCount = 1;

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
    if (remaining === 0) {
        remainingEl.style.color = '#16a34a'; // green - paid
    } else if (remaining < 0) {
        remainingEl.style.color = '#dc2626'; // red - overpaid
    } else {
        remainingEl.style.color = '#1a1a1a'; // black - unpaid
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
        <input class="compact-res-no" aria-label="Reservation Number" type="text" name="reservation_number" placeholder="0001" required maxlength="6" minlength="4" pattern="[0-9]{4,6}" inputmode="numeric" title="4-6 digit reservation number" oninput="updatePaymentReservationDropdowns()">
        <input class="compact-hotel" aria-label="Hotel Name" type="text" name="hotel" placeholder="Hotel Name">
        <input aria-label="Check In" type="date" name="check_in" placeholder="Check In">
        <input aria-label="Check Out" type="date" name="check_out" placeholder="Check Out">
        <input aria-label="Reservation Total" type="number" name="reservation_total" placeholder="Total SAR" step="0.01" required oninput="recalculate()">
        <button type="button" class="remove-btn" onclick="this.parentElement.remove(); recalculate(); updatePaymentReservationDropdowns();" aria-label="Remove reservation">×</button>
    `;
    container.appendChild(div);
    
    // Focus first input for convenience
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
        <button type="button" class="remove-btn" onclick="this.parentElement.remove(); recalculate();" aria-label="Remove payment">×</button>
    `;
    container.appendChild(div);
    updatePaymentReservationDropdowns();
    
    // Focus first input for convenience
    const first = div.querySelector('input[name="payment_date"]');
    if (first) first.focus();
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
 * Initialize on page load
 */
window.addEventListener('load', function() {
    recalculate();
    updatePaymentReservationDropdowns();
});
