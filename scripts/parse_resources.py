#!/usr/bin/env python3
"""Parse Isaiah 58:10 resource list into structured JSON for Beacon v2."""

import json
import re
from datetime import datetime

# Raw data from Isaiah 58:10 resource guide
# Format: Name\tAddress\tPhone\tURL\tDescription
RAW_STATEWIDE = """National Resource information\t\t211.org\tNational resource list
988 Suicide Hotline & Crisis Lifeline\t\t988\t988lifeline.org\tcall or text 988 or chat
Adoption Hotline\t\t800-432-9346\t\thotline
Adult Abuse Hotline\t\t800-752-6200\t\thotline
Adult and Child Health Hotline\t\t800-462-6122\t\thaline
Alcohol/Addiction Rehab Program\t\talcohol-addict.com\tfaith-based rehab program
Alcohol/Drug Hotline\t\t800-729-6686\t\thotline
Alcoholics Anonymous\t\t800-467-8091\t\t12-step recovery support
Appalachian Research & Defense Fund of KY\t\t866-277-5733\tFree legal assistance based on eligibility
ARC - Addiction Recovery Care\t\t888-351-1761 833-647-0674 606-638-0938\tarccenters.com\tResidential Treatment, Outpatient Treatment, ARC Anywhere, Bellefonte Hospital & Recovery Care, Karen's Place Maternity Center
Battered Women Justice Project\t\t800-903-0111\t\tDomestic violence hotline
Bluegrass First Steps\t\t800-454-2764\t\tMaternal/child health
Cabinet for Health and Family Services\t\t855-306-8959\t\tFood Stamps/Medical Card
Cancer Information Services\t\t800-422-6237\t\tCancer support hotline
CASA - Court Appointed Special Advocate for Children\t\t606-389-5968\tcasaclayknoxlaurel.com\tChild advocacy
Child Care Assistance\t\t855-306-8959\tkynect.ky.gov\tChild care subsidy
Child Protection Hotline\t\t877-597-2331\t\tReport child abuse
Child Support Information\t\t800-248-1163\t\tChild support enforcement
Child Support Voice Response\t\t800-443-1576\t\tChild support information
Community Based Services\t\t800-635-2570\t\tSocial services
Community Mental Health Centers\t\t800-928-8000\t\tMental health referrals
Consumer Product Safety Commission\t\t800-638-2772\t\tProduct safety
Crisis for Parents - 1-800-Children\t\t800-432-9251\t\tParenting crisis support
Crisis - General\t\t800-592-3980\t\tGeneral crisis hotline
Crisis Text Line\t\t741741\t\tText or call for crisis support
Cumberland River Behavioral Health\tBarbourville, Corbin, Harlan, London, Pineville, Manchester, McKee, Middlesboro, Mt. Vernon, Williamsburg\t606-896-2466 606-837-0100\tcrbhky.org\tInpatient and outpatient behavioral health services
Cumberland Valley Aging & Disability Resource\t\t606-877-5763\t\tSenior and disability services
Dept of Health and Human Services\t\tacf.hhs.gov\tFederal resources for homelessness, trafficking, refugees
Department for Housing\t\t800-669-9777\t\tHousing assistance
Department for Medicaid Services\t\t800-635-2570\t\tMedicaid enrollment
Domestic Violence Prevention Board\t\t800-258-3803\t\tDomestic violence hotline
Find Help Now KY\t\t833-8KY-HELP\t\tHelp line for services
Food and Drug Administration\t\t800-332-4010\t\tMedication and food safety
Food for the Poor\t\tfoodforthepoor.org\tFood assistance organization
Food Stamp Case Changes Reporting\t\t800-248-5861\t\tSNAP reporting
Foster Care Information\t\t800-232-5437\t\tFoster care information
Grace Health\t\t888-883-9005\tgracehealthky.org\tBehavioral health, Comprehensive Care, Medication Management, Targeted Case Management, Referral Services
Greyhound Free Ticket Home for Runaways\t\t1-800-786-2929\thttps://www.1800runaway.org/youth-teens/home-free\tFree bus ticket home for runaway youth
HHCK - Homeless & Housing Coalition of KY\t\t502-223-1834\thhck.org\tStatewide housing coalition
Home Health Agency Hotline\t\t800-635-6290\t\tHome health referrals
HomelessShelterDirectory\t\thomelessshelterdirectory.org\tNational shelter directory
Horizon Health\t\t606-657-2030\thorizonhealthky.org\tJob support, clothing, shoes, counseling, addiction recovery, women's housing, IOP, MAT, child care, peer support, mental health, behavioral health, youth services, employment, care coordination, harm reduction, ADHD testing, smoking cessation
Isaiah House\tChaplin, Louisville, Williamsburg, Willisburg, Versailles, Harrodsburg, Danville, Georgetown, Hillview, KY\t859-375-9200\tisaiah-house.org\tAddiction recovery: family/marriage/couples counseling, GED/college classes, job skill training, individual/group therapy, detox, DOC case management
Kentucky Attorney General's Office\t\t800-372-2551\t\tLegal hotline
Kentucky Domestic Violence Association\t\t502-209-5382\t\tDV support
Kentucky Harm Reduction Coalition\t1202 S. 3rd St #103, Louisville, KY 40203\t502-537-6061\tkyhrc.org\tHarm reduction education and supplies for substance use disorders
Kentucky Voices for Health\t\tkyvoicesforhealth.org\tHealth advocacy
KCEOC - Community Action Partnership\t\t606-546-3152\tkceoc.org\tSenior programs, energy assistance, summer food, weatherization, housing, youth homelessness, emergency support, career center, child development
KEJC - Kentucky Equal Justice Center\t\t859-788-2927\tkyequaljustice.org\tLegal aid
KFAN - Kentucky Food Action Network\t\tkyfoodactionnetwork.org\tFood security advocacy
KHC - Kentucky Housing Corporation\t\tkentuckiansinneed.org\tHousing Choice Voucher/Section 8
KTAP - Cash Assistance\t\t859-306-8959\tkynect.ky.gov\tBasic cash assistance for families with children
KY Help Statewide Call Center\t\t1-833-859-4357\tOperationUNITE.org/programs/kyhelp-call-center/\tSubstance use disorder assistance and family support
KY HIV/AIDS Program\t\t800-420-7431\t\tHIV/AIDS services
Kynect Health Coverage\t\t606-389-6708\tgracehealth.org\tHealth coverage enrollment
KY Pregnancy Help Centers\t\t859-255-5400\tkyfamily.org\tPregnancy support
La Red Nacional De Prevencion Del Suicidio\t\t888-628-9454\t988Lifeline.org\tSpanish language suicide prevention
Long Term Care Ombudsman\t\t800-372-2991\t\tNursing home advocacy
Medicaid Managed Care Ombudsman\t\t800-807-4027\t\tMedicaid advocacy
Medicare.gov\t\tmedicare.gov\tMedicare information
Mental Health Counseling\t\t800-928-8000\t\tMental health referrals
MHA - Mental Health America of KY\t\t859-684-7778\tmhaky.org\tMental health screenings, education, advocacy, system navigation
Mental Health Screenings Online 24/7\t\tmhascreening.org\tOnline mental health screening
Mental Health Support for KY Farmers\t\traisinghopeky.com\tFarm-specific mental health support
National Domestic Violence Hotline\t\t800-779-7233\t\tDV hotline
National Human Trafficking Hotline\t\t888-373-7888\t\tTrafficking hotline
National Lead Information Center\t\t800-424-5323\t\tLead poisoning info
National Maternal Mental Health Line\t\t833-943-5749\t\tMaternal mental health
National Network to End Domestic Violence\t\t202-543-5566\t\tDV advocacy
National Victim Notification Network\t\t800-511-1670\t\tVictim notification
National Sexual Assault Hotline\t\t800-656-4673\t\tRAINN sexual assault support
NEMT - Non-Emergency Medical Transportation\t\t\t\tMedicaid transportation to appointments
NOSW - New Opportunity School for Women\t\t859-985-7200\tnosw.org\tFree 2-week residential program in Berea: self-esteem, wellness, career, education, arts. Childcare/transportation reimbursement. Free online courses.
Operation UNITE\t350 C.A.P. Dr, London, KY 40744\t1-866-678-6483\tOperationUNITE.org\tSubstance misuse prevention and recovery facilitation
Oxford House\t1010 Wayne Ave Suite 300, Silver Spring, MD 20910\t301-587-2916\toxfordhouse.org\tPeer-run, self-sustaining, substance-free housing
Peacefully Whole Recovery\t\t859-412-2320\tpiecefullywhole.org\tHolistic recovery from alcohol, opioids, trauma. Serves 22 counties.
Pinnacle Treatment Centers\t\t606-922-2012\tpinnacletreatment.com\t24/7 admission, male/female beds, detox and residential
Poison Control\t\t800-222-1222\t\tPoison emergency
Prevent Child Abuse Kentucky\t\t800-432-9251\t\tChild abuse prevention
RAINN - Rape, Abuse and Incest National Network\t\t800-656-4673\t\tSexual assault support
Rape Crisis Hotline\t\t800-422-1060\t\tRape crisis support
Resource Center for Child Protection\t\t800-527-3232\t\tChild protection
Restoration Healthcare\t\trestorationhealthcare.com\tHealthcare services
Recovery Care - ARC\t332 River Bend Rd, Louisa, KY\t888-530-7632\tarccenters.com\tCasey's Law intervention, accepts Wellcare, United Health Care, Anthem
Serenity Ranch Recovery\t\t270-515-0212\tserenityranchrecovery.com\tKentucky's leading detox and rehab. 6 locations in KY and TN.
SID's Back to Sleep Campaign\t\t800-505-2742\t\tSafe sleep for infants
SNAP - Supplemental Nutrition Assistance\t\t855-306-8959\t\tFood assistance benefits
SOAR - Shaping Our Appalachian Region\t\t606-766-1160\tsoar.org\tRegional development
SOS Ministries Mission Field\t\t937-262-4100 855-696-2453\tsaveoursoulsministries.org\tPicks up and assists victims of trafficking and addiction. Provides safety and recovery support.
SPARC - Job Training\t1442 W. Steve Wariner Dr, Russell Springs, KY 42642\t859-396-0260\tsparcrecovery.com\tSobriety, peace, awareness, recovery, community
Special Needs Adoption\t\t800-423-9346\t\tSpecial needs adoption
Spouse Abuse Hotline\t\t800-544-2022\t\tSpouse abuse hotline
SHIP - State Health Insurance Assistance\t\t877-293-7447\t\tMedicare counseling
Suicide and Crisis Hotline\t\t988\t988lifeline.org\tCall or text 988
Target 4 Project\t\t606-878-7754 ext. 247\t\tFree HIV screening, Hepatitis C testing, PrEP referrals, Narcan, health education
Trevor Project - LGBTQ+ Youth\t\t866-488-7386\t\tLGBTQ+ youth crisis support
Trans Lifeline\t\t877-565-8860\t\tTransgender crisis support
VOA Mid-States Restorative Justice\t\t502-585-9920\t\tVictim healing and restoration
VOA Mid-States Recovery Community Center\t48 Owens Rd, Manchester, KY 40962\t606-658-9236\tFB: VOA Recovery Community Center\tSafe, supportive recovery community. Education, connections, support.
VOA Mid-States Employment Services\t\t606-765-3566\t\tEmployment for people in recovery
Vocal Kentucky\t723 S. Brook St, Louisville, KY 40203\t502-356-2322\tvocal-ky.org\tHarm reduction and advocacy
VOA Mid-States Freedom House\t1025 2nd St, Louisville, KY 40203\t502-635-4530\tvoamid.org/recovery\tTreatment without leaving children. Insurance assistance. Employment services.
Walker House Sober Living\tWinchester & Lexington, KY\t859-310-3567\twalkerhouseinc.com\tTransport, sober living, recovery, addiction/family/teen counseling, anxiety therapy
Welfare and Medicaid Fraud\t\t800-372-2970\t\tReport fraud
WIC - Women Infants and Children\t\t800-462-6122\t\tNutrition assistance
Women's Cancer Screening\t\t800-462-6122\t\tCancer screening
Winds of Change Counseling\t1220 Master St, Corbin, KY 40701\t606-515-3582 606-404-5104\twindsofchangeky.com\tSafe healing space, tailored professional services"""

RAW_VETERANS = """Combat Vets Association\t\t931-206-4043\t\tVeterans support
DAV - Disabled American Veterans\t\tdav.org\tVeterans with disabilities
GPS - Getting Peace for Those Who Served\t\t606-215-1417\t\tVeteran emotional support, readjustment therapy, family/marriage/substance abuse counseling, spiritual guidance, financial management, job placement
Homeless Veterans Reintegration Program\t\t606-866-4343 606-548-8977\tvivian.taylor@mtcomp.org\tResume prep, job searching, job resources for homeless veterans. Must be willing to work, non-dishonorable discharge.
Housing Voucher Programs Manchester KY\t\t877-424-3838\t\tVeteran housing vouchers
KY River Foothills SSVF\t\t800-372-7601\t\tTemporary rental assistance for qualifying veterans. POC: Lisa Roark.
National Veterans Foundation\t5777 West Century Blvd Suite 350, Los Angeles, CA 90045\t888-777-4443\tnvf.org\tVet-to-vet service, real solutions for veteran problems. Nationwide.
VFW - Veterans of Foreign Wars\t3027 W. Laurel Rd, London, KY 40741\t606-862-9336\t\tVeterans service organization
VOA Mid-States Veteran Services\t\twww.voamid.org\tMoral injury, preventing suicide, SSVF, homeless veterans reintegration"""

# County resources - structured as county sections
COUNTY_DATA = {
    "Bell": [
        ("Cumberland River RHOAR Center", "141 Tech Park Drive, Middlesboro, KY 40965", "606-248-4949", "crbhky.org", "Recovery, Hope, Opportunity and Resiliency. 100 women beds, 12 family reunification apartments, education & employment opportunities.")
    ],
    "Boone": [
        ("Ethan Health Addiction Treatment", "6159 1st Financial Dr, Burlington, KY 41005", "859-625-5235", "ethanhealth.org", "Intensive Outpatient Program. 24/7 support available.")
    ],
    "Clark": [
        ("Beacon of Hope", "Winchester, KY", "859-644-5171", None, "Emergency shelter with random drug testing.")
    ],
    "Clay": [
        ("Chad's Hope Center", "300 Chad McWhorter Ln, Manchester, KY 40962", "606-599-9716", None, None),
        ("Christian Appalachian Project", "Outreach RR4, Mt. Vernon, KY 40456", "606-256-4810", None, None),
        ("Community Outreach Center", "1 Fayette Properties 1-C, Manchester, KY 40962", "606-598-5127", None, None),
        ("Cumberland River Behavioral Health", "Manchester, KY", "606-598-5172", "crbhky.org", "Behavioral health services."),
        ("Cumberland Valley Aging & Disability Resource", None, "606-877-5763", None, "Senior and disability services."),
        ("Cumberland Valley Child Advocacy Center", None, "606-878-9116 1-877-597-2331", "cv-cac.org", "Child advocacy services."),
        ("Daniel Boone Community Action Agency", "1535 Shamrock Rd, Manchester, KY 40962", "606-598-5127", None, "CSBG Homeless Program."),
        ("Dismas Charities Manchester", "845 Muddy Gap Rd, Manchester, KY 40962", "606-598-5555", None, None),
        ("Emergency Shelter - Cumberland Valley DV Services", None, "606-256-9511 800-755-5348", "cvdvs.org", "20-bed emergency shelter for DV victims and children. Food, clothing, basic necessities."),
        ("Grief Support Group", "London, KY", "606-312-1513", None, "Contact Sharon Kidd."),
        ("Homeless and Housing Coalition of KY", None, None, "hhck.org", "Housing programs."),
        ("Housing Authority of Manchester", "306 Town Branch Rd, Manchester, KY 40962", "606-598-3884", "housingauthorityofmanchester.com", None),
        ("Isaiah 58:10 Ministries", "220 E. 4th St, London, KY 40741", "502-801-9119", "is5810.com", "Sack lunches, blankets, jackets, cold weather supplies, resource guides. Soup Kitchen Mon/Tues/Thurs/Fri/Sat 11am-1pm at Good Samaritan House."),
        ("Isaiah House", None, "859-375-9200", "isaiah-house.org", "Addiction Recovery Care."),
        ("Manchester Miracles", "Manchester, KY", "606-681-6060", None, "Sober living, clinical services, life skills, job assistance."),
        ("Mental Health - Cumberland River Comprehensive Care", "Rt. 9 Box 940, Manchester, KY 40962", "606-598-5172", "crbhky.org", "Community mental health, substance abuse, developmental disabilities, supportive living, children's services, First Steps."),
        ("Mommy & Me", None, "606-603-2486", None, "Helps women with children."),
        ("Mortgage and Credit Counseling - Apprisen", "2265 Harrodsburg Rd, Lexington, KY 40504", "800-355-2227", "apprisen.com", "HUD-approved counseling, mortgage delinquency, foreclosure prevention, reverse mortgage."),
        ("New Hope Counseling Recovery", None, "606-594-7479", "nhcr4u.com", "Inspiring hope, changing lives."),
        ("Red Bird Mission", "70 Queendale Center, Beverly, KY 40913", "606-598-0520", "rbmission.org", "Food, clothing, household items, furniture, transportation, GED, tax prep, prenatal education, daycare, school K-12."),
        ("VOA Recovery - Freedom House Manchester", "8467 US-421, Manchester, KY 40962", "606-603-2486", "voamid.org", "Recovery housing.")
    ],
    "Fayette": [
        ("BG Recovery", "711 E Loudon Ave, Lexington, KY 40505", "859-333-4128 214-566-1078", "bgrecovery.org", "Recovery education, IOP/OP, peer support, transportation, housing assistance."),
        ("Level Up Recovery", "1555 E. New Circle Rd Suite 190, Lexington, KY 40509", "859-329-1181 859-556-7401", None, "Drug & alcohol counseling, case management, peer support, intensive outpatient."),
        ("New Day Recovery Center", "711 E. Loudon Ave, Lexington, KY 40505", "859-749-4370 844-923-4357", "newdaycenter.com", None),
        ("Perfect Imperfections", "1018 E. New Circle Rd Ste 204, Lexington, KY 40505", "859-693-6089", "perfectimperfectionsky.com", "Licensed AODE, IOP, individual/group counseling, substance use counseling, case management, peer support, recovery housing."),
        ("Roaring Brook Recovery", "600 Perimeter Dr Ste 125, Lexington, KY 40517", "866-678-8123", "roaringbrookrecovery.com", "PHP, IOP, aftercare, men's/women's rehab, sober living, MAT, Hep-C treatment, alumni program."),
        ("Shepherds House", "635 Maxwelton Ct, Lexington, KY 40508", "859-252-1939 859-447-4020", "shepherdshouseinc.com", None),
        ("Still Waters Counseling", "828 Lane Allen Rd, Lexington, KY 40504", "859-399-1373 859-382-5687", "stillwaters.org", "IOP/OP group therapy, peer support, case management."),
        ("Voices of Hope", "644 N. Broadway, Lexington, KY 40508", "859-303-7671", "voicesofhopelex.org", "Recovery community center and support services."),
        ("Walker House", "Lexington, KY", "859-310-3567", "walkerhouseinc.com", "Sober living, recovery house, addiction/family/teen counseling, anxiety therapy.")
    ],
    "Floyd": [
        ("Floyd County Shelter", "Martin, KY", "606-949-2018", None, "Emergency shelter.")
    ],
    "Franklin": [
        ("Oxford House", "Frankfort, KY", "859-353-8452", "oxfordhouse.org", "Peer-run sober living. Must work. Takes people with children.")
    ],
    "Harlan": [
        ("4th Dimension Treatment Center", "Harlan, KY", "606-621-5007 606-273-2134", "4thdimentiontreatment.com", "Residential treatment, individual/group/family therapy, adventure therapy, 12-step, case management, peer support."),
        ("Lindsey Wilson University", "700 College Rd, Cumberland, KY 40823", "606-589-3075", "lindsey.edu", "Educational outreach and online programs."),
        ("Meridzo Center", "202 Church St, Lynch, KY 40855", "606-848-2766", "meridzo.org", "Distribution center, Hope House, Redeemed Living Transitions.")
    ],
    "Jessamine": [
        ("Clearview Behavioral Health", "1001 Park Central Ave, Nicholasville, KY 40356", "859-241-1096", None, "Behavioral health services. Intake: clearviewbehavioralhealth@gmail.com")
    ],
    "Jefferson": [
        ("Choose Hope LLC", "620 S. 3rd St Suite 101, Louisville, KY 40202", "502-631-5291", "choosehopellc.org", "Mental health/addiction treatment, therapeutic groups, alumni program, relapse prevention."),
        ("Pregnancy Center", "Louisville, KY", "502-640-1788", None, "Pregnancy support services."),
        ("YPR Young People in Recovery", "Louisville, KY", "502-821-6759", "youngpeopleinrecovery.org", "Recovery services for young people.")
    ],
    "Knox": [
        ("Apprisen", "2265 Harrodsburg Rd, Lexington, KY 40504", "800-355-2227", "apprisen.com", "HUD-approved counseling, mortgage delinquency, foreclosure prevention."),
        ("Christian Life Fellowship", "165 Black St, Barbourville, KY 40906", "606-546-9415", None, "Food assistance."),
        ("Church of the Nazarene Basket Ministry", "409 Master St, Corbin, KY 40701", "606-528-5935", None, None),
        ("Corbin Presbyterian Church", "601 Master Ct, Corbin, KY 40701", "606-528-1444", None, "Food assistance."),
        ("Corbin United Effort", "311 Barbourville St, Corbin, KY 40701", "606-528-7523", None, "Food pantry, meals, housing help, clothing, healthcare, system navigation."),
        ("CASA - Court Appointed Special Advocate", None, "606-389-5968", None, "Child advocacy."),
        ("Cumberland River Behavioral Health - Barbourville", "Barbourville, KY", "606-546-3104", "crbhky.org", "Behavioral health services."),
        ("Cumberland River Behavioral Health - Corbin", "Corbin, KY", "606-526-9459", "crbhky.org", "Behavioral health services."),
        ("Cumberland River Comprehensive Care Center", "American Greeting Card Rd, Corbin, KY 40701", "606-528-7010", "crbhky.org", "Community mental health, substance abuse, developmental disabilities, supportive living, children's services, First Steps."),
        ("Cumberland Valley DV Services", "P.O. Box 2162, London, KY 40456", "606-256-9511 800-755-5348", "cvdvs.org", "20-bed emergency shelter for DV victims. Food, clothing, necessities."),
        ("Emergency Fund Services", "P.O. Box 8, Barbourville, KY 40906", "606-546-3152", None, "Emergency assistance, food."),
        ("Feeding Souls for Jesus", "Parkway Ministries, Corbin, KY", "606-521-2349", "facebook.com/feedingsoulsforjesus", "Emergency food service."),
        ("First Baptist Church Barbourville", "201 N. Main St, Barbourville, KY", "606-546-3636", None, "Food assistance."),
        ("First United Methodist Church Barbourville", "312 N. Main St, Barbourville, KY", "606-546-3695", None, "Food assistance."),
        ("Hope Place Corbin", "409 Master St, Corbin, KY 40701", "606-215-6285", "hopeplaceky.org", "Transitional support."),
        ("Housing Authority of Corbin", "1336 Madison Ave, Corbin, KY 40701", "606-528-5104", "affordablehousing.com", None),
        ("Isaiah 58:10 Ministries", "220 E. 4th St, London, KY 40741", "502-801-9119", "is5810.com", "Sack lunches, cold weather supplies, resource guides, Soup Kitchen."),
        ("KCEOC Women's Emergency Support Center", "U.S. Hwy 25E, Barbourville, KY 40906", "606-546-3152", None, "Women and children. 15 semi-private beds. Meals, clothing, supportive services, transportation."),
        ("Mental Health - Cumberland River Comprehensive Care", "317 Cumberland Ave, Corbin, KY 40906", "606-546-3104", "crbhky.org", "Community mental health, substance abuse, developmental disabilities, supportive living, children's services, First Steps."),
        ("New Hope Counseling Recovery", None, "606-594-7479", "nhcr4.com", "Inspiring hope, changing lives."),
        ("New Hope Village Apartments", "P.O. Box 568, Corbin, KY 40701", "606-528-7010 ext 202", None, "11 one-bedroom units for mentally ill adults."),
        ("Appalachian Phoenix House", "401 Roy Kidd Ave, Corbin, KY 40701", "606-528-4381", None, "17-bed residential program for mentally ill men and women."),
        ("Redemption Road Recovery", "Barbourville, KY", "606-545-5169", None, None),
        ("The Everlasting Arm", "2006 S. Main St, Corbin, KY 40701", "606-528-3669", "theeverlastingarminc@gmail.com", "16-bed emergency shelter up to 90 days. Food and clothing bank.")
    ],
    "Lawrence": [
        ("ARC - Addiction Recovery Care", "16386 US-23, Louisa, KY 41230", "888-351-1761", "arccenters.com", "Addiction treatment, residential, transitional learning, outpatient, psychiatric hospital, primary care.")
    ],
    "Lincoln": [
        ("Turnersville Christian Mission", "200 Hwy 198, Stanford, KY 40484", "859-583-8155", None, "Community mission.")
    ],
    "Madison": [
        ("Dry Dock", "262 Four Mile Ave, Richmond, KY 40475", "859-575-7260", None, None),
        ("Ethan Health Addiction Treatment", "1623 Foxhaven Dr, Richmond, KY 40475", "859-625-5235", "ethanhealth.org", "Intensive Outpatient Program. 24/7 live chat."),
        ("Perfect Imperfections", "2161 Lexington Rd, Richmond, KY 40475", "859-368-0003", "perfectimperfectionsky.com", "Faith-based treatment facility. Accepts couples."),
        ("St. John Recovery for Men", "Richmond, KY", "859-300-1503", "stjohnrecoveryllc.com", "Behavioral health counseling, structured recovery housing."),
        ("Total Abstinence Behavioral Health", "230 Battlefield Memorial Hwy, Richmond, KY 40475", "859-408-7031", "totalabstinence24.com", "Behavioral health counseling."),
        ("Yonder Behavioral Health", "330 Hotel Court, Berea, KY 40403", "502-604-0228", "yonderbh.com", "Behavioral health services.")
    ],
    "Morgan": [
        ("New Vision Recovery Center", "559 Riverside Dr, West Liberty, KY 41472", "606-743-2107", None, "IOP/outpatient, 24-hour intake, drug screening, clinical & peer support, individualized treatment, case management, life skills.")
    ],
    "McCreary": [
        ("Housing Authority of Whitley City", "488 St Hwy 2792, Pine Knot, KY 42635", "606-354-2200", "affordablehousing.com", None),
        ("The Next Chapter - Men", "Whitley City, KY", "606-376-7416", None, "Faith-based. Provides transport."),
        ("The Next Chapter - Women", "Whitley City, KY", "606-376-7414", None, "Faith-based. Provides transport."),
        ("Whitley City Treatment Center", "Whitley City, KY", "423-560-6594", "recovery.org", None)
    ],
    "Perry": [
        ("Haven House Homeless Shelter", "Hazzard, KY", "606-436-5761", None, "Emergency shelter."),
        ("Housing Authority of Hazzard", "100 Campbell St Apt A, Hazzard, KY", "606-436-5741", "affordablehousing.com", None),
        ("Kentucky River Community Care", "Hazzard, KY", "606-436-1945", None, "Call 8:30am M-F."),
        ("Whispering Pines", "Hazzard, KY", "606-438-5929", "affordablehousing.com", "Affordable housing.")
    ],
    "Pulaski": [
        ("Bethany House Abuse Shelter", "Somerset, KY", "800-755-2017", None, "Abuse shelter."),
        ("God's Food Pantry", "119 S Central Ave, Somerset, KY", "606-679-8560", None, "Food assistance."),
        ("Help for Homeless", "Somerset, KY", "606-875-3893", None, "Homeless assistance."),
        ("High Street Baptist Church", "102 Bourne Ave, Somerset, KY", "606-678-8973", None, "Food assistance."),
        ("Housing Authority of Somerset", "400 Hail Knob Rd, Somerset, KY 42503", "606-679-1332", "affordablehousing.com", None),
        ("Lake Cumberland Recovery", "8294 US Hwy 27, Burnside, KY 42519", "606-341-1160", "lcrecovery.com", "24-hour intake. Genesis House (16-bed female), Lighthouse (48-bed male), Exodus Outpatient."),
        ("Life Abundant Ministries", "303 S. Main St, Somerset, KY", "606-677-0088", None, "Food assistance."),
        ("Open Arms Recovery Center", "166 Griffin Ave, Somerset, KY 42501", "859-494-2656", "openarmsrecovery.org", "Structured individualized treatment, long-term sobriety, harm reduction, community integration."),
        ("Pregnancy Center", "Somerset, KY", "859-300-1503", None, "Pregnancy support."),
        ("Somerset Community College", "808 Monticello St, Somerset, KY 42501", "606-451-6885", "somerset.kctcs.edu", "Human & Social Services classes."),
        ("United Way", "208 E. Mt Vernon St, Somerset, KY", "606-679-2974", None, "Food assistance.")
    ],
    "Taylor": [
        ("Blessings of Hope", "315 Bradfordsville Rd, Campbellsville, KY 42718", "717-824-1227", "blessingsofhope.com", "Food procurement.")
    ],
    "Washington": [
        ("Cumberland Mountain Healthcare", "323 Main St, Williamsburg, KY 40769", "606-825-6011", None, "Psychiatry, family care, AODE certified, weight loss, wellness memberships.")
    ],
    "Whitley": [
        ("Anchored Ministries", "Williamsburg, KY", "606-765-7336", None, "Free if no insurance."),
        ("Appalachian Phoenix House", "401 Roy Kidd Ave, Corbin, KY 40741", "606-528-4381", None, "17-bed residential for mentally ill. Independent living skills focus."),
        ("Baptist Health Trillium Center", "1 Trillium Way #5, Corbin, KY 40701", "606-528-1212", "baptisthealth.com", "Detox services."),
        ("Bell-Whitley Community Action Agency", "U.S. Hwy 25W, Williamsburg, KY 40769", "606-549-3933", None, "Food, shelter, natural disaster emergency funds."),
        ("Catholic Church", "76 W. Sycamore St, Williamsburg, KY", "606-549-2156", None, "Food assistance."),
        ("Cedaridge Ministries", "Factory Ln, Williamsburg, KY", "606-549-1373", None, "Food assistance."),
        ("Corbin United Effort", "311 Barbourville St, Corbin, KY 40701", "606-528-7523", None, "Rental assistance, supportive services, food pantry, utilities."),
        ("Cumberland River Behavioral Health - Corbin", "Corbin, KY", "606-526-9459", "crbhky.org", "Behavioral health."),
        ("Cumberland River Behavioral Health - Williamsburg", "Williamsburg, KY", "606-549-1440", "crbhky.org", "Behavioral health."),
        ("Cumberland Valley DV Services", "P.O. Box 2162, London, KY 40456", "606-256-9511 606-843-2022 800-755-5348", "cvdvs.org", "20-bed emergency shelter for DV victims and children."),
        ("Cumberland Valley Regional Housing Authority", "221 N. 3rd St, Williamsburg, KY 40769", None, "affordablehousing.com", None),
        ("Emergency Christian Ministries", "630 South Hwy 25, Williamsburg, KY 40769", "606-549-2922 606-400-1464", None, "75 beds. Men, women, children. Food, clothing, supportive services."),
        ("Feeding Souls for Jesus", "Parkway Ministries, Corbin, KY", "606-521-2349", "facebook.com/feedingsoulsforjesus", "Emergency food service."),
        ("First Baptist Church Corbin", "401 N. Laurel Ave, Corbin, KY 40701", "606-528-4738", None, "Food assistance."),
        ("First Baptist Church Williamsburg", "230 5th St, Williamsburg, KY", "606-549-0280", None, "Food assistance."),
        ("Hope Place Corbin", "409 Master St, Corbin, KY 40701", "606-215-6285", "hopeplaceky.org", "Transitional support."),
        ("Independence House", None, "606-523-9386", None, "Substance abuse treatment for women. 5-bed transitional (6 months) and 10-bed short-term (30 days)."),
        ("Isaiah 58:10 Ministries", "220 E. 4th St, London, KY 40741", "502-801-9119", "is5810.com", "Sack lunches, cold weather supplies, resource guides, Soup Kitchen."),
        ("Medical/Mental Health - Cumberland River Comprehensive Care", "P.O. Box 84, Williamsburg, KY 40769", "606-549-1440", "crbhky.org", "Community mental health, substance abuse, developmental disabilities, supportive living, children's services, First Steps."),
        ("Mortgage/Credit Counseling - Apprisen", "2265 Harrodsburg Rd, Lexington, KY 40504", "800-355-2227", "apprisen.com", "HUD-approved counseling, foreclosure prevention, reverse mortgage."),
        ("Mountain Outreach", "Williamsburg, KY", "800-343-1609", "ucumberlands.edu", "Food assistance, minor home repairs, house builds, construction projects."),
        ("Mercy Mountain Housing", "1866 Whetstone Rd, Rockholds, KY 40759", "866-338-0557", None, "Rental and acquisition for transitional and permanent housing."),
        ("Whitley County Health Department", "368 Penny Ln, Williamsburg, KY 40769", "606-549-3380", "whitleycountyhealthdepartment.com", "Clinical services, public health."),
        ("Williamsburg Housing Authority", "600 Brush Arbour Church Rd, Williamsburg, KY", "606-549-0282", "affordablehousing.com", None)
    ]
}

# Need mappings based on keywords
NEED_KEYWORDS = {
    "food": ["food", "meal", "pantry", "feed", "soup", "lunch", "wic", "snap", "nutrition", "hungry"],
    "shelter": ["shelter", "emergency shelter", "beds", "sleep", "warming", "white flag", "overnight"],
    "housing": ["housing", "rental", "apartment", "section 8", "voucher", "transitional housing", "permanent housing", "sober living", "recovery house"],
    "clothing": ["clothing", "clothes", "blanket", "jacket", "sleeping bag", "hygiene", "supplies"],
    "health": ["medical", "health", "hospital", "clinic", "dental", "hiv", "hepatitis", "nemt", "pharmacy", "medicare", "medicaid"],
    "mental-health": ["mental health", "counseling", "therapy", "psychiatric", "behavioral health", "psychotherapy", "screening"],
    "addiction": ["addiction", "recovery", "substance", "drug", "alcohol", "detox", "rehab", "iop", "treatment", "mat", "sober"],
    "crisis": ["crisis", "hotline", "suicide", "lifeline", "emergency", "abuse", "trafficking", "violence"],
    "documents": ["id", "birth certificate", "social security", "documents", "identification"],
    "jobs": ["job", "employment", "work", "career", "training", "resume", "ged"],
    "legal": ["legal", "law", "court", "attorney", "justice", "expungement"],
    "family": ["child", "youth", "family", "parent", "pregnancy", "prenatal", "baby", "kid", "foster", "maternity"],
    "transportation": ["transport", "bus", "ride", "vehicle", "nemt"],
    "education": ["education", "ged", "school", "college", "learning", "literacy", "classes"],
    "veterans": ["veteran", "vfw", "dav", "va ", "ssvf"],
    "community": ["peer", "community", "support group", "celebrate recovery", "aa ", "na ", "meeting"]
}

SERVICE_TYPE_KEYWORDS = {
    "hotline": ["hotline", "call", "text", "lifeline"],
    "walk-in": ["walk-in", "walk in", "show up", "drop-in"],
    "residential": ["residential", "beds", "shelter", "housing", "sober living", "recovery house", "apartment"],
    "outpatient": ["outpatient", "iop", "php", "counseling", "therapy"],
    "mobile": ["mobile", "outreach", "delivery", "van"],
    "online": ["online", "website", "telehealth", "virtual", "app"],
    "peer-led": ["peer", "peer-run", "self-sustaining", "support group"],
    "faith-based": ["church", "ministry", "faith", "baptist", "methodist", "catholic", "nazarene", "christ"],
    "government": ["government", "department", "state", "federal", "county"]
}

POPULATION_KEYWORDS = {
    "families": ["family", "families", "children", "kids", "parent", "maternity", "pregnant"],
    "women": ["women", "woman", "female", "maternity", "battered"],
    "men": ["men", "man", "male"],
    "youth": ["youth", "young", "teen", "adolescent", "child"],
    "seniors": ["senior", "elder", "aging", "old"],
    "veterans": ["veteran", "vfw", "dav", "military"],
    "lgbtq+": ["lgbtq", "gay", "lesbian", "transgender", "queer"],
    "disability": ["disability", "disabled", "handicap", "ada"],
    "re-entry": ["re-entry", "reentry", "justice", "incarceration", "parole", "probation"],
    "substance-use": ["substance", "addiction", "drug", "alcohol", "active use"]
}


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:80].strip('-')


def parse_phones(phone_str):
    if not phone_str:
        return []
    phones = re.findall(r'[\d][\d()-]{6,}(?:\s*ext\.?\s*\d+)?', phone_str)
    return [p.strip() for p in phones if len(p.strip()) >= 7]


def detect_needs(name, desc):
    text = f"{name} {desc}".lower()
    needs = []
    for need, keywords in NEED_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            needs.append(need)
    return needs or ["community"]


def detect_service_types(name, desc):
    text = f"{name} {desc}".lower()
    types = []
    for st, keywords in SERVICE_TYPE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            types.append(st)
    return types or ["walk-in"]


def detect_populations(name, desc):
    text = f"{name} {desc}".lower()
    pops = []
    for pop, keywords in POPULATION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            pops.append(pop)
    return pops or ["anyone"]


def detect_cost(name, desc):
    text = f"{name} {desc}".lower()
    if "free" in text or "no cost" in text:
        return "free"
    if "sliding" in text or "scale" in text:
        return "sliding-scale"
    if "insurance" in text or "medicaid" in text:
        return "insurance"
    if "private" in text or "pay" in text:
        return "private-pay"
    return "unknown"


def build_resource(name, address, phone, url, description, county, source="Isaiah 58:10 Ministries"):
    phones = parse_phones(phone)
    needs = detect_needs(name, description or "")
    service_types = detect_service_types(name, description or "")
    populations = detect_populations(name, description or "")
    cost = detect_cost(name, description or "")

    # Parse address components
    city = None
    state = "KY"
    zip_code = None
    if address:
        # Try to extract city, state, zip
        m = re.search(r',\s*([A-Za-z .]+),?\s*KY\s*(\d{5})?', address)
        if m:
            city = m.group(1).strip()
            zip_code = m.group(2)
        else:
            m2 = re.search(r',\s*([A-Za-z .]+)', address)
            if m2:
                city = m2.group(1).strip()
    
    # Determine service type from context
    status = "needs-verification"
    intake = None
    hours = None
    eligibility = None
    notes = None

    desc_lower = (description or "").lower()
    if "24/7" in desc_lower or "24 hour" in desc_lower:
        hours = "24/7"
    if "call ahead" in desc_lower:
        intake = "Call ahead recommended"
    if "must" in desc_lower and ("pass" in desc_lower or "provide" in desc_lower or "willing" in desc_lower):
        # Extract eligibility-like sentences
        eligibility = description
    if "soup kitchen" in desc_lower:
        if not hours:
            hours = "Mon/Tues/Thurs/Fri/Sat 11am-1pm"
        notes = "Soup Kitchen on-site"

    resource_id = f"{county.lower()}-{slugify(name)}" if county != "Statewide" else slugify(name)

    # Auto-generate map URL from address
    map_url = None
    if address and address != "Statewide":
        map_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"

    # Detect languages from description
    languages = ["English"]
    desc_lower_check = (description or "").lower()
    if "spanish" in desc_lower_check or "español" in desc_lower_check:
        languages.append("Spanish")

    # Detect if referral is needed
    referral_required = None
    if "referral" in desc_lower_check:
        referral_required = True

    # Detect what to bring from description
    what_to_bring = None
    if "must" in desc_lower_check and ("provide" in desc_lower_check or "bring" in desc_lower_check or "have" in desc_lower_check):
        what_to_bring = description

    return {
        "id": resource_id,
        "name": name,
        "alternate_names": [],
        "description": description or "",
        "address": address or "Statewide",
        "city": city,
        "state": state,
        "zip": zip_code,
        "county": county,
        "latitude": None,
        "longitude": None,
        "phones": phones,
        "email": None,
        "url": url if url and url.startswith("http") else (f"https://{url}" if url else None),
        "facebook": None,
        "needs": needs,
        "service_types": service_types,
        "populations": populations,
        "eligibility": eligibility,
        "cost": cost,
        "hours": hours,
        "languages": languages,
        "what_to_bring": what_to_bring,
        "referral_required": referral_required,
        "intake_hours": None,
        "map_url": map_url,
        "status": "active",
        "intake_process": intake,
        "capacity": None,
        "waitlist": None,
        "accepts_insurance": None,
        "last_verified": "2026-09-20",
        "verified_by": "initial-import",
        "confidence": "medium",
        "source_urls": ["https://is5810.com/main/resources/"],
        "first_seen": "2026-09-20",
        "tags": [],
        "notes": notes,
        "related": []
    }


def main():
    resources = []
    seen = set()

    # Parse statewide
    for line in RAW_STATEWIDE.strip().split("\n"):
        parts = line.strip().split("\t")
        if len(parts) < 4:
            continue
        name = parts[0].strip()
        address = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        phone = parts[2].strip() if len(parts) > 2 else ""
        url = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
        desc = parts[4].strip() if len(parts) > 4 else ""

        r = build_resource(name, address, phone, url, desc, "Statewide")
        if r["id"] not in seen:
            resources.append(r)
            seen.add(r["id"])

    # Parse veterans
    for line in RAW_VETERANS.strip().split("\n"):
        parts = line.strip().split("\t")
        if len(parts) < 4:
            continue
        name = parts[0].strip()
        address = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        phone = parts[2].strip() if len(parts) > 2 else ""
        url = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
        desc = parts[4].strip() if len(parts) > 4 else ""

        r = build_resource(name, address, phone, url, desc, "Statewide")
        if r["id"] not in seen:
            resources.append(r)
            seen.add(r["id"])

    # Parse county data
    for county, entries in COUNTY_DATA.items():
        for entry in entries:
            name, address, phone, url, desc = entry
            r = build_resource(name, address, phone, url, desc, county)

            # Check for duplicates (same org in statewide)
            slug = slugify(name)
            merged = False
            for existing in resources:
                if slugify(existing["name"]) == slug:
                    if county not in existing["county"]:
                        existing["county"] = county
                    if phones := parse_phones(phone):
                        for p in phones:
                            if p not in existing["phones"]:
                                existing["phones"].append(p)
                    if url and not existing["url"]:
                        existing["url"] = url if url.startswith("http") else f"https://{url}"
                    if desc and not existing["description"]:
                        existing["description"] = desc
                    merged = True
                    break

            if not merged and r["id"] not in seen:
                resources.append(r)
                seen.add(r["id"])

    # Sort
    resources.sort(key=lambda r: r["name"].lower())

    # Metadata
    counties = sorted(set(r["county"] for r in resources if r["county"] != "Statewide"))
    all_needs = sorted(set(n for r in resources for n in r["needs"]))
    all_service_types = sorted(set(s for r in resources for s in r["service_types"]))
    all_populations = sorted(set(p for r in resources for p in r["populations"]))

    output = {
        "metadata": {
            "version": "2.0",
            "source": "Isaiah 58:10 Ministries & Outreach",
            "source_url": "https://is5810.com/main/resources/",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "total_resources": len(resources),
            "states": ["KY"],
            "regions": {"KY": counties + ["Statewide"]},
            "needs": all_needs,
            "service_types": all_service_types,
            "populations": all_populations
        },
        "resources": resources
    }

    with open("/tmp/beacon/data/resources.json", "w") as f:
        json.dump(output, f, indent=2)

    # By county
    import os
    os.makedirs("/tmp/beacon/data/resources-by-county", exist_ok=True)
    by_county = {}
    for r in resources:
        c = r["county"]
        by_county.setdefault(c, []).append(r)
    for county, items in by_county.items():
        fname = county.lower().replace(" ", "-")
        with open(f"/tmp/beacon/data/resources-by-county/{fname}.json", "w") as f:
            json.dump({"county": county, "count": len(items), "resources": items}, f, indent=2)

    # By need
    os.makedirs("/tmp/beacon/data/resources-by-need", exist_ok=True)
    by_need = {}
    for r in resources:
        for n in r["needs"]:
            by_need.setdefault(n, []).append(r)
    for need, items in by_need.items():
        with open(f"/tmp/beacon/data/resources-by-need/{need}.json", "w") as f:
            json.dump({"need": need, "count": len(items), "resources": items}, f, indent=2)

    # By state
    os.makedirs("/tmp/beacon/data/resources-by-state", exist_ok=True)
    with open("/tmp/beacon/data/resources-by-state/ky.json", "w") as f:
        json.dump({"state": "KY", "count": len(resources), "resources": resources}, f, indent=2)

    # Index (lightweight)
    index = []
    for r in resources:
        index.append({
            "id": r["id"],
            "name": r["name"],
            "county": r["county"],
            "city": r["city"],
            "needs": r["needs"],
            "phones": r["phones"],
            "address": r["address"],
            "status": r["status"],
            "confidence": r["confidence"]
        })
    with open("/tmp/beacon/data/index.json", "w") as f:
        json.dump(index, f, indent=2)

    print(f"Built {len(resources)} resources")
    print(f"Counties: {counties}")
    print(f"Needs: {all_needs}")
    print(f"Service types: {all_service_types}")
    print(f"Populations: {all_populations}")


if __name__ == "__main__":
    main()
