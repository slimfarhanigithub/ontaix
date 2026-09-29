# Tessaline Telecom Operations Process Framework

Tessaline Telecom is a fictional organisation, and this document was written as evaluation material.

## Introduction

This handbook describes how Tessaline Telecom plans, delivers, supports and charges for its mobile and fibre services. It is written for operations staff, team leads and the people who design new products, and it is meant to be read alongside the local work instructions that each desk maintains.

The framework gives every team a shared vocabulary. When a customer calls about a late installation, a wrong bill or a slow connection, everyone should be able to name the process that owns the problem and the record that shows where it stands.

The framework is layered. At the top sit the operating domains, below them the processes that each domain runs, then the individual activities within each process, and finally the records, documents and artefacts those activities create or consume. Each section below walks down one domain from the top layer to the bottom one.

The handbook describes the target way of working. Where a desk still works differently, the desk lead records the gap in the operations change log and agrees a date to close it. The change log is reviewed every month, and gaps older than two quarters are escalated.

## Context

Tessaline Telecom serves roughly 2.4 million mobile subscribers and 610,000 fibre households across a mid-sized coastal market. The company started as a regional fibre builder, acquired a mobile network twelve years later, and spent much of the following decade bringing two sets of teams, tools and habits together. The result worked, but it worked differently in each building.

The rewrite of this framework had several drivers, and none of them was new. Most had been visible in customer complaints for years before anyone connected them. Customers increasingly buy converged offers, so a single order can touch a mobile network, a fibre network and a billing account at the same time. The regulator has tightened reporting on installation delays and fault restoration, and it expects the same figures to be traceable back to individual orders and tickets. The finance team wants fewer billing corrections, because every correction costs a call, a credit and some goodwill.

The mission of operations is simple to state and hard to do: deliver what was sold, keep it working, and charge for it correctly. The framework does not change that mission. It makes the path from one step to the next visible, so that hand-offs stop being the place where customers get lost.

The market remains competitive. Two larger operators and several resellers compete on price, and Tessaline Telecom has chosen to compete on reliability and on honest bills instead. That choice only works if operations can prove, month after month, that orders arrive on time, faults are fixed quickly and invoices are right the first time.

## How The Framework Is Organised

Tessaline Telecom organises its operations into Fulfilment, Assurance, Billing and the Product catalogue. Fulfilment turns a sale into a working service. Assurance keeps the service working and restores it when it fails. Billing turns usage and subscriptions into invoices and cash. The Product catalogue defines what can be sold and at what price, and every other part of operations reads from it.

Each domain has a domain owner who reports to the Chief Operating Officer. The domain owner is accountable for the end-to-end result, including the parts delivered by partners such as installation contractors and the payment service provider.

The processes below are described in the order a customer meets them. A new customer first meets fulfilment, then lives with assurance and billing for years, while the catalogue quietly shapes every one of those encounters.

## Fulfilment

Fulfilment consists of order handling, service configuration and activation, resource provisioning and fibre installation. A mobile order normally passes through the first three in minutes, while a fibre order waits for a technician visit and can take one to three weeks. The domain is measured on how quickly and how reliably a customer goes from signature to working service.

### Order Handling

Order handling consists of order capture, order decomposition, order tracking and order closure. The order desk runs this work for retail, online and business channels alike, so a customer sees the same behaviour whichever way they buy.

Order capture produces a customer order. It starts when a sales agent, a shop assistant or the online shop submits a basket, and it ends when the order is accepted into the order management system. Order capture reads the Product catalogue to confirm that each item is still on sale and correctly priced.

Each customer order contains one order line for every product, add-on or piece of equipment the customer has chosen. Order lines carry their own status, which matters for converged orders because the mobile part usually finishes long before the fibre part.

Order capture includes an eligibility check before the order is accepted. The eligibility check consists of an address check and a credit check. The address check confirms that the premises can be served by fibre and records the nearest distribution point. The credit check reads the customer's payment history from payment handling and sets a spending limit for postpaid customers.

Order decomposition produces a service order and a resource order from each accepted customer order. The service order describes what the customer will experience, such as a mobile line or a fibre connection at a given speed. The resource order describes what the network must supply, such as a number, a port or a piece of equipment.

Order tracking raises a jeopardy alert when an order is at risk of missing its promised date. The alert goes to the order desk lead, who decides whether to contact the customer, escalate to a partner or re-plan the work.

Order closure happens once every order line is complete. At that point the customer is told what was delivered and when charging starts, which removes a common cause of first-bill disputes.

### Service Configuration And Activation

Service configuration and activation consists of service activation and service testing. This work takes the service order and turns it into something the customer can actually use.

Service activation includes SIM activation and fibre line activation. Service activation starts usage collection for the new service, so that usage from the very first call or session reaches the billing platforms.

SIM activation handles two SIM formats: the eSIM profile and the physical SIM card. An eSIM profile is downloaded to the handset over the air after the customer scans a code. A physical SIM card is paired with the line in the shop or activated by the customer on first use.

Fibre line activation applies a line profile that sets the speed and quality settings for the connection. Fibre line activation configures the OLT port that was reserved earlier for the customer's address.

Service testing produces an activation test report for every new service. The report records the test calls, the measured speeds and any retries, and it stays attached to the order for ninety days.

### Resource Provisioning

Resource provisioning consists of number allocation, port allocation and inventory update. The network inventory is the single source of truth for what is free, reserved and in use.

Number allocation assigns a mobile number from the free pool or confirms a number ported in from another operator. Port allocation reserves an OLT port in the exchange that serves the customer's address. Inventory update marks every allocated resource as in use once activation succeeds, and releases it again if the order is cancelled.

Resource provisioning is fully automated for mobile orders. For fibre orders, a planner reviews any address where the exchange is close to capacity before the port is reserved.

### Fibre Installation

Fibre installation consists of appointment scheduling, field installation and installation acceptance. Most installations are carried out by contractors, but the method, the records and the quality standard belong to Tessaline Telecom.

Appointment scheduling books an installation appointment in a two-hour window chosen by the customer. The appointment is confirmed by text message the day before and can be moved up to four hours before the window starts.

Field installation requires a field technician and an installation kit. The field technician is trained and certified by Tessaline Telecom even when employed by a contractor. The installation kit contains an optical network terminal and a drop cable. The optical network terminal is the box that terminates the fibre inside the home. The drop cable connects the home to the nearest distribution point in the street.

Installation acceptance requires a customer sign-off on the technician's handheld device. The sign-off confirms that the service works in at least one room and that the site was left clean. Without it the order cannot close, and the technician's visit is not paid.

## Assurance

Assurance consists of problem handling, service quality management, resource trouble management and SLA management. Where fulfilment is measured in days, assurance is measured in minutes and hours, and the domain runs around the clock.

### Problem Handling

Problem handling consists of ticket intake, fault diagnosis, problem resolution and problem closure. Problem handling has three support tiers: first-line support, second-line support and field support. First-line support answers calls and chats and resolves simple faults on the spot. Second-line support takes faults that need network access or specialist knowledge. Field support sends a technician to the customer's premises or to the street cabinet.

Ticket intake creates a customer trouble ticket for every reported fault, whether it arrives by phone, chat, app or shop. Each customer trouble ticket is ranked by the impact on the customer. A business customer with a total outage is always ranked first.

Fault diagnosis runs a line test before any technician is sent. The line test queries the optical network terminal for fibre faults, and checks handset registration and cell status for mobile faults.

Problem resolution applies a workaround when a full repair will take longer than the customer can reasonably wait. A typical workaround is a temporary mobile data boost for a fibre customer whose line is down.

Problem closure happens only once the customer confirms the fault is gone. The customer's feedback is stored on the ticket and feeds the monthly review of the support tiers.

### Service Quality Management

Service quality management consists of quality monitoring and quality improvement. It looks at the experience of groups of customers rather than single faults.

Quality monitoring tracks each service quality indicator by area, by technology and by hour. The service quality indicators include dropped call rate and download speed. Dropped call rate is measured for every mobile cell. Download speed is measured by test probes placed in fibre homes and on the mobile network.

Quality improvement produces an improvement plan whenever an indicator stays below target for four weeks in a row. The improvement plan names an owner, a budget and a date, and it is reviewed at the monthly operations board.

### Resource Trouble Management

Resource trouble management consists of alarm handling and resource repair. It deals with the network itself, often before any customer notices a problem.

Alarm handling processes every network alarm raised by the mobile and fibre equipment. A critical alarm is a kind of network alarm that signals a loss of service for more than one hundred customers. Alarm handling raises a customer trouble ticket on behalf of affected customers when a critical alarm lasts longer than fifteen minutes.

Resource repair issues a work order for every fault that needs physical intervention. Each work order is assigned to a field technician with the right skills and the nearest location.

### SLA Management

SLA management consists of SLA monitoring, SLA violation handling and SLA reporting. It applies to business customers and wholesale partners, who buy services with contractual commitments.

SLA monitoring checks each service level agreement against measured performance every hour. Each service level agreement defines an availability target and a restoration target. The availability target is usually expressed as a monthly percentage, and the restoration target as a number of hours from ticket creation. SLA monitoring reads each service quality indicator that is relevant to the contract.

SLA violation handling calculates a service credit when a target is missed. The account manager is informed before the customer is, so the conversation happens before the invoice arrives.

SLA reporting publishes a monthly report to every business customer, showing performance against each target and the credits applied.

## Billing

Billing consists of usage mediation, rating, bill run, payment handling and dispute management. Billing is the domain where small errors become visible to customers, so each part of it ends with a control.

### Usage Mediation

Usage mediation consists of usage collection and usage validation. Usage collection gathers a usage record for every call, message and data session from the network elements. A voice usage record is a kind of usage record that holds the calling number, the called number and the duration. A data usage record is a type of usage record that holds the volume and the access point used.

Usage validation rejects repeated and incomplete records, because network elements sometimes resend records after an outage. Rejected records go to a suspense queue that the mediation team clears every working day.

### Rating

Rating consists of tariff lookup, charge calculation and allowance tracking. Tariff lookup maintains the tariff table used by every rating decision. Tariff lookup reads prices from the Product catalogue each night and publishes a new version of the table.

Charge calculation produces a rated event for each priced call, message or session, carrying the price, the tax category and the allowance consumed.

Allowance tracking decrements the data allowance of each subscriber as sessions are rated. When the data allowance runs out, the customer receives a text and can buy an extra pack.

### Bill Run

The bill run consists of invoice generation and bill validation. Each bill run covers one billing cycle, and Tessaline runs four cycles per month so that the workload is spread evenly.

Invoice generation produces a customer invoice for every active account in the cycle. Each customer invoice contains an invoice line for every subscription, one-off charge, usage total and credit. Each invoice line carries a tax amount calculated at the rate valid on the service date. Invoice generation applies each service credit that has been approved for the period.

Bill validation takes place before invoices are released. The billing operations lead reviews a random selection of invoices, together with every invoice whose total changed by more than thirty percent since the previous cycle.

### Payment Handling

Payment handling consists of payment collection and dunning. Payment collection has two payment methods: direct debit, card payment and bank transfer. Direct debit is the default for postpaid customers and accounts for most collected revenue. Card payment is used for prepaid top-ups and for one-off charges. Bank transfer is mainly used by business customers who pay against a purchase order.

Dunning triggers service suspension when an invoice remains unpaid forty-five days after its due date. Before that point the customer receives reminders by text and email, and a call from the collections team. Service suspension blocks outgoing calls and data but keeps emergency calls available.

### Dispute Management

Dispute management consists of dispute intake, dispute investigation and dispute resolution. Dispute intake registers a billing dispute and pauses dunning on the disputed amount. Dispute investigation reads the rated events behind the disputed charges and compares them with the tariff that applied. Dispute resolution issues a credit note when the investigation finds in the customer's favour. The credit note appears on the next invoice the customer receives.

## Product Catalogue

The Product catalogue has two product lines: mobile plans and fibre broadband bundles. The catalogue is owned by the product team, but it is maintained under operational change control because every other domain depends on it.

Mobile plans include the prepaid plan and the postpaid plan. Tessa Go is a kind of prepaid plan with a monthly bundle of data and minutes that the customer tops up by card. Tessa Unlimited is a kind of postpaid plan with unlimited calls and texts and a generous amount of data. Tessa Unlimited includes an EU roaming allowance that customers can use while travelling in the European Union.

Fibre broadband bundles include the Fibre 300 bundle and the Fibre Max bundle. The Fibre 300 bundle offers 300 megabits per second and suits most households. The Fibre Max bundle includes a mesh Wi-Fi kit for larger homes, and it offers speeds of up to two gigabits per second.

A converged customer usually holds one mobile plan and one fibre bundle on the same account. The catalogue records which combinations earn a loyalty discount, and the discount is applied at order capture rather than at the bill run.

## Roles And Accountabilities

The Chief Operating Officer chairs the monthly operations board and owns the framework as a whole. Each domain owner is accountable for the targets of their domain and for the quality of the records their teams create.

The order desk lead is responsible for day-to-day order flow and for deciding what happens when a jeopardy alert is raised. The field operations manager manages the relationship with installation contractors and signs off their monthly performance. The network operations centre manager runs the round-the-clock monitoring of the network and chairs the daily incident review.

The billing operations lead signs off every bill run before invoices are released. The revenue assurance analyst compares usage, rated volumes and invoiced totals each month and investigates any gap above an agreed tolerance. The customer care director owns the experience of customers who call about faults or bills, and reads the satisfaction scores every week.

The product manager for each product line owns the commercial content of the catalogue. Any change that affects the price or the eligibility rules must be tested by the billing operations lead before it goes live.

## Key Performance Indicators

Every domain reports a small set of indicators to the monthly operations board. The indicators are chosen so that each one can be traced back to the individual records that produced it.

| Indicator | Domain | Target |
| --- | --- | --- |
| Order-to-activation time for mobile | Fulfilment | Under two hours. |
| Installation on first appointment | Fulfilment | Above 92 percent. |
| Mean time to restore | Assurance | Under six hours. |
| Bill accuracy rate | Billing | Above 99.6 percent. |
| Disputes per thousand invoices | Billing | Below 3. |

The order-to-activation time for mobile is measured from order acceptance to the first successful network registration. Installation on first appointment counts the fibre orders completed at the first booked visit, without a second trip. Mean time to restore is measured from ticket creation to confirmed restoration, and it excludes time when the customer could not be reached.

The bill accuracy rate counts invoices that were not later corrected by a credit note or a rebill. The figure for disputes per thousand invoices is reported by cause, so that the product team can see which plans generate confusion.

## Systems

Tessaline Telecom supports this framework with a small number of core platforms. Orbis is the order management system used by the order desk and the online shop. Stratum holds the network inventory for both mobile and fibre resources.

Vigil is the fault management platform used by the network operations centre and by second-line support. Meter is the mediation platform that receives records from the network elements. Ledgerline is the billing platform that holds accounts, tariffs and invoices.

Each platform has a named owner who approves configuration changes and keeps the platform documentation current. The owners meet every fortnight to agree release dates, because a change in one platform often needs a matching change in another. The platforms exchange messages through a shared integration layer. No team is allowed to build a direct database connection between two platforms, because such connections have caused silent data loss in the past.

## Working Principles

A few principles apply across the whole framework, whatever the domain. They are deliberately short, because a principle that needs a page of explanation is usually a rule in disguise.

Every hand-off leaves a record. When work passes from one team to another, the receiving team must be able to see what was done, by whom and when, without asking. A phone call or a chat message can speed things up, but it never replaces the record.

The customer hears one voice. However many teams are involved behind the scenes, the customer should be told what is happening by one person or one channel, and should never receive contradictory messages on the same day.

Automation comes after clarity. A task is automated only once the manual version is stable, measured and written down. Automating a confused task simply produces confusion faster, and it makes the confusion harder to see.

Exceptions are visible. Any team may make an exception to protect a customer, but the exception must be logged with a reason, and the log is reviewed at the monthly operations board. A pattern of similar exceptions is treated as a signal that the framework itself needs to change.

Numbers are shared. Every team can see the indicators of every other team, so that a delay upstream is understood downstream before it becomes a complaint. The operations dashboard is open to all staff, including contractors working on Tessaline Telecom orders.

## Training And Onboarding

New staff in operations spend their first two weeks learning the framework before they work on live customers. The training follows a single converged order from the shop counter to the first paid invoice, so that each person sees how their own desk fits into the wider picture.

Contractor technicians receive a shorter version focused on installation standards, safety and the records they must complete on site. Refresher sessions are held every year, and whenever the board approves a significant change to the handbook.

## Governance And Change

Changes to this framework are proposed by any domain owner and approved by the monthly operations board. A proposal states which activities change, which records are affected and how the change will be measured after it goes live.

Catalogue changes follow a lighter path when they only adjust prices within existing plans. A new plan, a new bundle or a new add-on always goes through the full board review, because it touches every domain at once.

Each domain owner reviews the handbook section for their domain once a year. The review checks that the activities described here still match what the teams actually do, and it records any deliberate exception together with its expiry date.

The framework is a living document. When teams find a better way of working, the right response is to change the handbook through the board, not to work around it quietly.
