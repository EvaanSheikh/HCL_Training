import { primaryFinding } from '../lib/format.js';

const multiFindings = [
  {
    "type": "descriptive_statistics",
    "metric": "Quantity",
    "mean": 2.54,
    "value": 2.54,
    "stats": { "count": 500003, "mean": 2.54, "min": 1, "max": 35 }
  },
  {
    "type": "descriptive_statistics",
    "metric": "UnitSellingPrice",
    "mean": 183.86,
    "value": 183.86,
    "stats": { "count": 500003, "mean": 183.86, "min": 4.74, "max": 1977.34 }
  },
  {
    "type": "descriptive_statistics",
    "metric": "sales",
    "mean": 420.4387518824887,
    "value": 420.4387518824887,
    "stats": {
      "count": 500003,
      "mean": 420.4387518824887,
      "median": 143.0605,
      "min": 3.4930000000000003,
      "max": 35535.474,
      "sum": 210220637.2575
    },
    "message": "Average sales: 420.44 (median: 143.06, min: 3.49, max: 35,535.47, total sum: 210,220,637.26 across 500,003 records)."
  }
];

// Test 1: Query specifically for sales
const primary = primaryFinding(multiFindings, "What are the average sales across all records?");
console.log('Target finding matching user query:');
console.log(JSON.stringify(primary, null, 2));

if (primary?.metric !== "Average sales" || Math.abs((primary?.value ?? 0) - 420.44) > 0.01) {
  console.error("FAILED to pick sales metric!");
  process.exit(1);
}
console.log("SUCCESS: primaryFinding correctly prioritized 'sales' over earlier metrics based on user query!");
