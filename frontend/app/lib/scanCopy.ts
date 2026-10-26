// English copy for the free scan (home → /results), which stays English while the paid
// reports are Dutch. The backend ships Dutch text for findings, actions and assumptions;
// this page renders its own wording keyed on their stable ids instead.

import type { ActionItem, ClientAssumption, DataConflict } from "~/lib/types";

export const FINDING_EN: Record<string, { title: string; body: string }> = {
  "perf.lcp_mobile": {
    title: "Mobile visitors wait too long to see your products",
    body: "Every second past 2.5s before the main content appears costs conversions.",
  },
  "adtraffic.post_click_bounce": {
    title: "Paid clicks leave before the page loads",
    body: "Visitors you paid for bounce because the page is still loading.",
  },
  "perf.inp_mobile": {
    title: "Pages respond slowly to taps and clicks",
    body: "Heavy scripts make buttons and menus feel broken on mobile.",
  },
  "perf.cls_mobile": {
    title: "Content jumps while the page loads",
    body: "Elements shifting under the visitor's thumb erode trust.",
  },
  "checkout.no_guest": {
    title: "Checkout forces account creation",
    body: "One of the most common reasons shoppers abandon checkout.",
  },
  "checkout.address_fields": {
    title: "The address form asks for too much",
    body: "Every extra field at checkout costs completed orders.",
  },
  "checkout.no_express_pay": {
    title: "No express payment buttons found",
    body: "Worth checking by hand — these often load after the page does.",
  },
  "cro.social_proof": {
    title: "No reviews or ratings found",
    body: "Shoppers look for proof that others bought and liked it before they commit.",
  },
  "shipping.cost_clarity": {
    title: "Shipping costs only show up at checkout",
    body: "Unexpected extra costs are the most-cited reason shoppers abandon checkout.",
  },
  "seo.rich_results": {
    title: "Your products don't stand out in Google",
    body: "Price, stock and star ratings aren't passed to Google as structured data.",
  },
};

export const ACTION_EN: Record<string, { title: string; body: string }> = {
  "speed.lcp": {
    title: "Get mobile load time under 2.5 seconds",
    body: "Compress and preload the hero image, defer render-blocking scripts, remove apps nobody uses.",
  },
  "speed.inp": {
    title: "Make pages respond instantly",
    body: "Load chat, pop-ups and tracking after the first interaction — or drop them.",
  },
  "layout.cls": {
    title: "Stop content from jumping",
    body: "Give images, banners and widgets fixed dimensions.",
  },
  "checkout.guest": {
    title: "Allow guest checkout",
    body: "Offer account creation after the order, not before it.",
  },
  "checkout.fields": {
    title: "Shorten the address form",
    body: "Drop or make optional every field delivery doesn't need; add address autocomplete.",
  },
  "checkout.express": {
    title: "Check your express payment buttons",
    body: "On a phone, confirm Shop Pay, Apple Pay and Google Pay show in cart and checkout.",
  },
  "cro.social_proof": {
    title: "Show reviews and star ratings",
    body: "On product and collection pages — and pass the rating to Google for stars in search.",
  },
  "shipping.clarity": {
    title: "Show shipping costs on the product page",
    body: "Put costs and the free-shipping threshold next to the buy button and in the announcement bar.",
  },
  "seo.structured_data": {
    title: "Pass price, stock and ratings to Google",
    body: "Add product and review data as structured data on product pages.",
  },
  "tracking.attribution": {
    title: "Have your tracking validated",
    body: "Pixels, consent mode v2 and server-side tracking, so ad platforms see what converts.",
  },
};

export const EFFORT_EN: Record<ActionItem["effort"], string> = { S: "Small", M: "Medium", L: "Large" };

export const ASSUMPTION_EN: Record<string, string> = {
  monthly_sessions: "Visitors per month",
  conversion_rate: "Conversion rate",
  aov_eur: "Average order value",
  monthly_revenue_eur: "Monthly revenue (visitors × conversion × order value)",
  mobile_share: "Mobile share of traffic",
  paid_share: "Paid share of traffic",
  monthly_ad_spend_eur: "Monthly ad spend",
};

export const SOURCE_EN: Record<ClientAssumption["source"], string> = {
  operator: "your input",
  seranking: "measured",
  derived: "calculated",
  benchmark: "industry average",
};

export function conflictMessageEn(c: DataConflict): string {
  if (c.kind === "revenue_vs_funnel") {
    return `The revenue you entered doesn't add up with your visitor numbers (${c.ratio.toFixed(1)}x apart). We priced everything on what your traffic can carry — double-check revenue and visitors.`;
  }
  if (c.kind === "ad_spend_vs_revenue") {
    return "The ad spend entered is unusually high relative to revenue — one of the inputs is likely off.";
  }
  return "Your mobile and overall conversion rates don't add up — check both.";
}
