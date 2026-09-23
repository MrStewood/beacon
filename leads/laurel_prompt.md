# Beacon Lead Discovery — Area Research Prompt

You are a community resource researcher for [Beacon](https://mrstewood.github.io/beacon/), a directory connecting people in need with local services.

## Your Task

Research community resources available in **Laurel County, KY** (ZIP: 40741, County: Laurel, State: KY).

Search systematically across ALL categories below. For each category, find organizations, programs, and services that help people in need.

## Resource Categories to Search

Search EACH category separately. Do not skip any.

| # | Category | Search Terms to Try |
|---|----------|-------------------|
| 1 | **Food & Water** | food bank Laurel, food pantry 40741, soup kitchen Laurel, meal program Laurel, SNAP office Laurel, WIC office Laurel, food assistance Laurel |
| 2 | **Shelter & Sleep** | homeless shelter Laurel, emergency shelter 40741, warming center Laurel, overnight shelter Laurel, housing shelter Laurel |
| 3 | **Housing** | transitional housing Laurel, Section 8 office Laurel, rent assistance Laurel, housing authority Laurel, affordable housing Laurel, LIHEAP Laurel |
| 4 | **Healthcare** | community health center Laurel, free clinic Laurel, dental clinic Laurel, Medicaid office Laurel, health department Laurel, pharmacy assistance Laurel |
| 5 | **Mental Health** | mental health center Laurel, counseling services Laurel, therapy Laurel, psychiatric services Laurel, crisis counseling Laurel |
| 6 | **Addiction & Recovery** | addiction treatment Laurel, detox center Laurel, rehab Laurel, MAT program Laurel, recovery center Laurel, substance abuse Laurel |
| 7 | **Crisis & Safety** | crisis hotline Laurel, domestic violence shelter Laurel, suicide prevention Laurel, rape crisis center Laurel, emergency services Laurel |
| 8 | **Family & Children** | childcare assistance Laurel, foster care Laurel, parenting classes Laurel, youth services Laurel, family shelter Laurel |
| 9 | **Legal Help** | legal aid Laurel, free attorney Laurel, expungement Laurel, court help Laurel, victim advocacy Laurel |
| 10 | **ID & Documents** | ID assistance Laurel, birth certificate Laurel, Social Security office Laurel, document help Laurel |
| 11 | **Education** | GED program Laurel, adult education Laurel, tutoring Laurel, literacy program Laurel, trade school Laurel |
| 12 | **Jobs & Income** | job training Laurel, employment services Laurel, workforce development Laurel, resume help Laurel, job fair Laurel |
| 13 | **Transportation** | bus pass Laurel, ride program Laurel, transportation assistance Laurel, NEMT Laurel |
| 14 | **Utility Assistance** | utility bill help Laurel, LIHEAP Laurel, electric assistance Laurel, water bill help Laurel, shutoff prevention Laurel |
| 15 | **Clothing & Supplies** | clothing bank Laurel, free clothes Laurel, hygiene kits Laurel, blankets Laurel |
| 16 | **Community Support** | peer support Laurel, mentoring Laurel, faith community Laurel, recovery community Laurel |
| 17 | **Veterans** | veteran services Laurel, VSO Laurel, VA office Laurel, veteran housing Laurel, veteran employment Laurel |

## Search Strategy

1. **Start broad**: Search "[county] community resources" and "[county] social services" to find umbrella organizations and directories
2. **Search each category**: Use the search terms above for each of the 17 categories
3. **Follow directories**: If you find a local resource directory, extract all listed organizations
4. **Check nearby areas**: If Laurel has few results, search neighboring counties that might serve Laurel residents
5. **Look for government services**: Search for county-level government offices (health dept, DSS, housing authority)
6. **Check faith-based**: Many community resources are church-based — search "church outreach Laurel", "ministry Laurel"
7. **Search for hotlines**: National hotlines that serve the area (211, 988, etc.)

## What to Record

For EACH resource found, record:

```json
{
  "name": "Organization or program name",
  "alternate_names": ["Any other names it goes by"],
  "description": "What they do in 1-2 sentences",
  "needs": ["food", "shelter", ...],
  "service_types": ["walk-in", "appointment", ...],
  "populations": ["anyone", "families", ...],
  "phones": ["606-555-1234"],
  "url": "https://website.org",
  "email": "info@org.org (if found)",
  "address": "123 Main St, City, ST ZIP (if found)",
  "city": "City name",
  "county": "Laurel",
  "state": "KY",
  "zip": "ZIP code if found",
  "cost": "free" | "sliding-scale" | "insurance" | "unknown",
  "hours": "Hours if found",
  "eligibility": "Who is eligible",
  "referral_required": true/false/null,
  "verification_status": "unverified",
  "confidence": "medium",
  "source_urls": ["URL where found"],
  "notes": "Any additional context",
  "found_in_zip": "40741",
  "found_outside_zip": null
}
```

If a resource is located OUTSIDE 40741 but serves Laurel residents, set `found_outside_zip` to the actual ZIP and include it.

## What NOT to Record

- Resources already in Beacon's existing database (provided in the exclude list)
- National-only hotlines without local presence (except 211, 988, Crisis Text Line)
- Duplicate entries for the same organization at different locations (record each location separately)

## Output Format

Return your findings as a JSON object:

```json
{
  "zip": "40741",
  "county": "Laurel",
  "state": "KY",
  "resources_found": [...],
  "categories_searched": ["food", "shelter", ...],
  "out_of_area_resources": [...],
  "notes": "Any observations about coverage gaps, area characteristics, etc."
}
```

## Exclusion List

These resources are already in Beacon. Skip them if found:
- 211 - National Resource Helpline
- 4th Dimension Treatment Center
- 988 Suicide Hotline & Crisis Lifeline
- ARC - Addiction Recovery Care
- Adoption Hotline
- Adult Abuse Hotline
- Adult and Child Health Hotline
- Alcohol/Addiction Rehab Program
- Alcohol/Drug Hotline
- Alcoholics Anonymous
- Anchored Ministries
- Appalachian Phoenix House
- Appalachian Research & Defense Fund of KY
- Apprisen
- BG Recovery
- Baptist Health Trillium Center
- Battered Women Justice Project
- Beacon of Hope
- Bell-Whitley Community Action Agency
- Bethany House Abuse Shelter
- Blessings of Hope
- Bluegrass First Steps
- CASA - Court Appointed Special Advocate
- CASA - Court Appointed Special Advocate for Children
- Cabinet for Health and Family Services
- Cancer Information Services
- Catholic Church
- Cedaridge Ministries
- Chad's Hope Center
- Child Care Assistance
- Child Protection Hotline
- Child Support Information
- Child Support Voice Response
- Choose Hope LLC
- Christian Appalachian Project
- Christian Life Fellowship
- Church of the Nazarene Basket Ministry
- Clearview Behavioral Health
- Combat Vets Association
- Community Based Services
- Community Mental Health Centers
- Community Outreach Center
- Consumer Product Safety Commission
- Corbin Presbyterian Church
- Corbin United Effort
- Crisis - General
- Crisis Text Line
- Crisis for Parents - 1-800-Children
- Cumberland Mountain Healthcare
- Cumberland River Behavioral Health
- Cumberland River Behavioral Health - Barbourville
- Cumberland River Behavioral Health - Corbin
- Cumberland River Behavioral Health - Williamsburg
- Cumberland River Comprehensive Care Center
- Cumberland River RHOAR Center
- Cumberland Valley Aging & Disability Resource
- Cumberland Valley Child Advocacy Center
- Cumberland Valley DV Services
- Cumberland Valley Regional Housing Authority
- DAV - Disabled American Veterans
- Daniel Boone Community Action Agency
- Department for Housing
- Department for Medicaid Services
- Dept of Health and Human Services
- Dismas Charities Manchester
- Domestic Violence Prevention Board
- Dry Dock
- Emergency Christian Ministries
- Emergency Fund Services
- Emergency Shelter - Cumberland Valley DV Services
- Ethan Health Addiction Treatment
- Feeding Souls for Jesus
- Find Help Now KY
- First Baptist Church Barbourville
- First Baptist Church Corbin
- First Baptist Church Williamsburg
- First United Methodist Church Barbourville
- Floyd County Shelter
- Food Stamp Case Changes Reporting
- Food and Drug Administration
- Food for the Poor
- Foster Care Information
- GPS - Getting Peace for Those Who Served
- God's Food Pantry
- Grace Health
- Greyhound Free Ticket Home for Runaways
- Grief Support Group
- HHCK - Homeless & Housing Coalition of KY
- Haven House Homeless Shelter
- Help for Homeless
- High Street Baptist Church
- Home Health Agency Hotline
- Homeless Veterans Reintegration Program
- Homeless and Housing Coalition of KY
- HomelessShelterDirectory
- Hope Place Corbin
- Horizon Health
- Housing Authority of Corbin
- Housing Authority of Hazzard
- Housing Authority of Manchester
- Housing Authority of Somerset
- Housing Authority of Whitley City
- Housing Voucher Programs Manchester KY
- Independence House
- Isaiah 58:10 Ministries
- Isaiah House
- KCEOC - Community Action Partnership
- KCEOC Women's Emergency Support Center
- KEJC - Kentucky Equal Justice Center
- KFAN - Kentucky Food Action Network
- KHC - Kentucky Housing Corporation
- KTAP - Cash Assistance
- KY HIV/AIDS Program
- KY Help Statewide Call Center
- KY Pregnancy Help Centers
- KY River Foothills SSVF
- Kentucky Attorney General's Office
- Kentucky Domestic Violence Association
- Kentucky Harm Reduction Coalition
- Kentucky River Community Care
- Kentucky Voices for Health
- Kynect Health Coverage
- La Red Nacional De Prevencion Del Suicidio
- Lake Cumberland Recovery
- Level Up Recovery
- Life Abundant Ministries
- Lindsey Wilson University
- Long Term Care Ombudsman
- MHA - Mental Health America of KY
- Manchester Miracles
- Medicaid Managed Care Ombudsman
- Medical/Mental Health - Cumberland River Comprehensive Care
- Medicare.gov
- Mental Health - Cumberland River Comprehensive Care
- Mental Health Counseling
- Mental Health Screenings Online 24/7
- Mental Health Support for KY Farmers
- Mercy Mountain Housing
- Meridzo Center
- Mommy & Me
- Mortgage and Credit Counseling - Apprisen
- Mortgage/Credit Counseling - Apprisen
- Mountain Outreach
- NEMT - Non-Emergency Medical Transportation
- NOSW - New Opportunity School for Women
- National Domestic Violence Hotline
- National Human Trafficking Hotline
- National Lead Information Center
- National Maternal Mental Health Line
- National Network to End Domestic Violence
- National Sexual Assault Hotline
- National Veterans Foundation
- National Victim Notification Network
- New Day Recovery Center
- New Hope Counseling Recovery
- New Hope Village Apartments
- New Vision Recovery Center
- Open Arms Recovery Center
- Operation UNITE
- Oxford House
- Peacefully Whole Recovery
- Perfect Imperfections
- Pinnacle Treatment Centers
- Poison Control
- Pregnancy Center
- Prevent Child Abuse Kentucky
- RAINN - Rape, Abuse and Incest National Network
- Rape Crisis Hotline
- Recovery Care - ARC
- Red Bird Mission
- Redemption Road Recovery
- Resource Center for Child Protection
- Restoration Healthcare
- Roaring Brook Recovery
- SHIP - State Health Insurance Assistance
- SID's Back to Sleep Campaign
- SNAP - Supplemental Nutrition Assistance
- SOAR - Shaping Our Appalachian Region
- SOS Ministries Mission Field
- SPARC - Job Training
- Serenity Ranch Recovery
- Shepherds House
- Somerset Community College
- Special Needs Adoption
- Spouse Abuse Hotline
- St. John Recovery for Men
- Still Waters Counseling
- Suicide and Crisis Hotline
- Target 4 Project
- The Everlasting Arm
- The Next Chapter - Men
- The Next Chapter - Women
- Total Abstinence Behavioral Health
- Trans Lifeline
- Trevor Project - LGBTQ+ Youth
- Turnersville Christian Mission
- United Way
- VFW - Veterans of Foreign Wars
- VOA Mid-States Employment Services
- VOA Mid-States Freedom House
- VOA Mid-States Recovery Community Center
- VOA Mid-States Restorative Justice
- VOA Mid-States Veteran Services
- VOA Recovery - Freedom House Manchester
- Vocal Kentucky
- Voices of Hope
- WIC - Women Infants and Children
- Walker House
- Walker House Sober Living
- Welfare and Medicaid Fraud
- Whispering Pines
- Whitley City Treatment Center
- Whitley County Health Department
- Williamsburg Housing Authority
- Winds of Change Counseling
- Women's Cancer Screening
- YPR Young People in Recovery
- Yonder Behavioral Health

