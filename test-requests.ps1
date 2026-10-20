# Test requests for the HRIS Support Ticket Tracker (Windows PowerShell)
# Replace the URL below with your own API Gateway invoke URL.
# Run the commands one at a time rather than pasting the whole file.

$api = "https://YOUR-API-ID.execute-api.ap-southeast-1.amazonaws.com"

# 1. Create a ticket
$t = Invoke-RestMethod -Method Post -Uri "$api/tickets" -ContentType "application/json" -Body '{
  "customerName": "Sample Company A",
  "module": "Core HR",
  "requestType": "Access/Permission",
  "priority": "High",
  "description": "Manager cannot view team records; needs role updated."
}'
$t

# 2. List everything, then filter (status uses the status-index GSI)
Invoke-RestMethod -Uri "$api/tickets"
Invoke-RestMethod -Uri "$api/tickets?status=Open"
Invoke-RestMethod -Uri "$api/tickets?status=Open&module=Payroll"

# 3. Get one ticket
Invoke-RestMethod -Uri "$api/tickets/$($t.ticketId)"

# 4. Work the ticket
Invoke-RestMethod -Method Put -Uri "$api/tickets/$($t.ticketId)" -ContentType "application/json" -Body '{"status":"Resolved","assignee":"Your Name","resolutionNotes":"Updated role permissions; customer confirmed access."}'

# 5. Summary report
Invoke-RestMethod -Uri "$api/summary" | ConvertTo-Json

# 6. A Critical ticket (should trigger the email alert)
Invoke-RestMethod -Method Post -Uri "$api/tickets" -ContentType "application/json" -Body '{"customerName":"Sample Company D","module":"Payroll","requestType":"Issue/Bug","priority":"Critical","description":"Payroll run failed to post for all employees."}'

# 7. Error handling (PowerShell prints these as red errors, which is expected)
Invoke-RestMethod -Method Post -Uri "$api/tickets" -ContentType "application/json" -Body '{"module":"Nope"}'
Invoke-RestMethod -Uri "$api/tickets/HRIS-DOESNOTEXIST"

# 8. Delete
Invoke-RestMethod -Method Delete -Uri "$api/tickets/$($t.ticketId)"
