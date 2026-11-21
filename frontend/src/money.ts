/** The application works in one currency: the Philippine peso (PHP, ₱). Keep in step with backend/travel_planner/currency.py. */
export const CURRENCY = "PHP";
export const PESO = "₱";

const formatter = new Intl.NumberFormat("en-PH", { style: "currency", currency: CURRENCY, maximumFractionDigits: 0 });

/** An amount in pesos, for example ₱30,300. */
export const money = (n: number) => formatter.format(n);

/** A signed difference, for example +₱1,200 or −₱500. */
export const signed = (n: number) => (n > 0 ? "+" : n < 0 ? "−" : "") + money(Math.abs(n));
