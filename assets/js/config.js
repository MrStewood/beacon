/**
 * Beacon Shared Configuration
 *
 * Central definition of labels, categories, and constants.
 * Loaded by index.html, widget.js, and print pages.
 *
 * To update categories: edit schema/categories.json, then regenerate this file.
 */

const BEACON_CONFIG = {
  version: "2.0.0",

  // Need labels (human-readable names for category IDs)
  needs: {
    addiction: "Addiction & Recovery",
    clothing: "Clothing & Supplies",
    community: "Community Support",
    crisis: "Crisis & Safety",
    documents: "ID & Documents",
    education: "Education",
    family: "Family & Children",
    food: "Food & Water",
    health: "Healthcare",
    housing: "Housing",
    jobs: "Jobs & Income",
    legal: "Legal Help",
    "mental-health": "Mental Health",
    shelter: "Shelter & Sleep",
    transportation: "Transportation",
    veterans: "Veterans"
  },

  // Service type labels
  serviceTypes: {
    hotline: "Hotline",
    "walk-in": "Walk-In",
    appointment: "Appointment",
    residential: "Residential",
    outpatient: "Outpatient",
    mobile: "Mobile / Outreach",
    online: "Online",
    "peer-led": "Peer-Led",
    "faith-based": "Faith-Based",
    government: "Government"
  },

  // Population labels
  populations: {
    anyone: "Open to All",
    families: "Families",
    women: "Women",
    men: "Men",
    youth: "Youth",
    seniors: "Seniors",
    veterans: "Veterans",
    "lgbtq+": "LGBTQ+",
    disability: "Disability",
    "re-entry": "Re-Entry",
    pregnant: "Pregnant",
    "substance-use": "Active Substance Use",
    recovery: "In Recovery"
  },

  // Cost labels
  cost: {
    free: "Free",
    "sliding-scale": "Sliding Scale",
    insurance: "Insurance Accepted",
    "private-pay": "Private Pay",
    unknown: "Cost Unknown"
  },

  // Crisis resources (always shown prominently)
  crisis: {
    "911": { name: "Emergency Services", phone: "911", description: "For immediate danger to life or property" },
    "988": { name: "Suicide & Crisis Lifeline", phone: "988", description: "24/7 crisis support, call or text 988" },
    "211": { name: "Community Resource Helpline", phone: "211", description: "Local services and referrals" },
    "741741": { name: "Crisis Text Line", phone: "741741", description: "Text HOME to 741741" }
  },

  // Data URL (absolute, for widget and external use)
  dataUrl: "https://mrstewood.github.io/beacon/data/resources.json"
};

// Make available in all contexts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BEACON_CONFIG;
}
