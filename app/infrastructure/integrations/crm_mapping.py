from typing import Set


LEAD_UPDATE_EVENT_TYPES: Set[str] = {
    # Appointments -> Appointment
    "AppointmentCreate",
    "AppointmentUpdate",
    "AppointmentDelete",

    # Contacts -> ContactCard
    "ContactCreate",
    "ContactUpdate",
    "ContactDelete",
    "ContactTagUpdate",

    # Opportunities -> Lead
    "OpportunityAssignedToUpdate",
    "OpportunityCreate",
    "OpportunityDelete",
    "OpportunityMonetaryValueUpdate",
    "OpportunityStageUpdate",
    "OpportunityStatusUpdate",
    "OpportunityUpdate",
}
