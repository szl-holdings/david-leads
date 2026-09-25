# SPDX-License-Identifier: Apache-2.0
"""Person and private-residence screen for EPA ECHO facility names.

ECHO ``FAC_NAME`` is free text supplied by permitting programs. Some permits
cover a single private residence (for example a small-flow or single-residence
sewage system) and carry a household's name, a house-number street address, or
both. The ECHO projection declares ``person_or_contact`` and
``street_or_geolocation`` as excluded categories, so the ingestor rejects such
rows before serialization and both snapshot verifiers refuse a bundle that
still carries one.

The screen is a deterministic heuristic over the facility name and NAICS codes
only. It is not identity resolution: it can reject an organization whose name
reads like a person, and it can miss an unusual personal name. It uses the
standard library only because the Space image copies ``app/`` but not the
ingestion tooling, and the ingestor and the runtime must apply the same rule.
"""
from __future__ import annotations

import re
from typing import Iterable

REJECTION_REASON = "PERSON_OR_RESIDENCE_NAME"

PRIVATE_HOUSEHOLD_NAICS = "814110"  # NAICS: Private Households

# Residential permit designations and residence words. HOUSEHOLD is not
# counted when it introduces a household-hazardous-waste program.
_RESIDENTIAL = re.compile(
    r"\b(?:SRSTP|SFTF|SFS|SFR|HSTS|HOMEOWNER|RES|RESIDENCE|PROP"
    r"|SINGLE[\s-]+FAMILY|HOUSEHOLD(?![\s-]+HAZARDOUS))\b"
)

# Words that make a residential designation belong to an organization. Kept
# narrow on purpose: generic words such as COUNTY, CHURCH, SCHOOL, STATE, or CO
# also occur in road names and must not rescue a residence row.
_ORGANIZATION_MARKERS = frozenset(
    """
    LLC INC INCORPORATED CORP CORPORATION COMPANY LTD LLP LLLP LP PLLC
    ASSN ASSOC ASSOCIATION HOA POA CONDOMINIUM CONDO COOPERATIVE COOP
    HOTEL MOTEL INN RESORT SUITES MUNICIPAL MUNICIPALITY AUTHORITY
    """.split()
)
_GOVERNMENT_OF = re.compile(r"\b(?:CITY|TOWN|TOWNSHIP|BOROUGH|COUNTY|VILLAGE)\s+OF\b")

# A house number, an optional directional, one to three street-name words, and
# a street type. Seven-digit and longer numbers (parcel or permit numbers) and
# a number directly followed by a street type (for example "2 ST ...") do not
# match.
_STREET_ADDRESS = re.compile(
    r"(?<![0-9A-Z])[0-9]{1,6}[A-Z]?\s+(?:[NSEW]\.?\s+)?(?:[A-Z0-9'\-]+\.?\s+){1,3}"
    r"(?:ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE|HWY|HIGHWAY"
    r"|WAY|CT|COURT|PL|PLACE|PKWY|PARKWAY|CIR|CIRCLE|TER|TERRACE|TRL|TRAIL|PIKE"
    r"|TPKE|TURNPIKE|ROUTE|RT)\b"
)

_DBA = re.compile(r"\b(?:D/?B/?A|T/?A|A/?K/?A)\b.*$")  # doing/trading as
_ESTATE_OF = re.compile(r"^(?:THE\s+)?(?:ESTATE|EST)\s+OF\s+")
_TOKEN_SPLIT = re.compile(r"[^A-Z0-9'&\-]+")
_NAME_WORD = re.compile(r"[A-Z]+(?:['\-][A-Z]+)*")
_DIGIT = re.compile(r"[0-9]")

# Generational and credential affixes carried by personal names.
_NAME_AFFIXES = frozenset("JR SR II III IV MD DDS DVM DO ESQ CPA PHD RN".split())

# Sewage-system descriptors that follow a household name on residential
# discharge permits. They are removed before the person-shape test.
_SEPTIC_DESCRIPTORS = frozenset(
    "STP SEWAGE TREATMENT PLANT SYSTEM SEPTIC WWTP WWTF TP DISCHARGE".split()
)

# Common US given names (general knowledge, not an authoritative list). Names
# that double as ordinary English or business words are left out.
_GIVEN_NAMES = frozenset(
    """
    JAMES JOHN ROBERT MICHAEL WILLIAM DAVID RICHARD JOSEPH THOMAS CHARLES
    CHRISTOPHER DANIEL MATTHEW ANTHONY DONALD STEVEN PAUL ANDREW JOSHUA KENNETH
    KEVIN BRIAN GEORGE TIMOTHY RONALD EDWARD JASON JEFFREY RYAN JACOB GARY
    NICHOLAS ERIC JONATHAN STEPHEN LARRY JUSTIN SCOTT BRANDON BENJAMIN SAMUEL
    GREGORY ALEXANDER PATRICK JACK DENNIS JERRY TYLER AARON JOSE ADAM NATHAN
    HENRY ZACHARY DOUGLAS PETER KYLE NOAH ETHAN JEREMY WALTER KEITH ROGER TERRY
    HAROLD SEAN CARL ARTHUR LAWRENCE DYLAN JESSE JORDAN BRYAN BILLY BRUCE
    GABRIEL JOE LOGAN ALBERT WILLIE ALAN EUGENE RUSSELL VINCENT PHILIP BOBBY
    JOHNNY BRADLEY ROY RALPH RANDY LOUIS HARRY WAYNE HOWARD FRED ERNEST MARTIN
    CRAIG STANLEY SHAWN TRAVIS PHILLIP LEONARD EARL DALE JIMMY RODNEY TODD
    NORMAN ALLEN MARVIN GLENN JEFFERY DARRELL CURTIS FRANCIS LEROY CLARENCE
    DERRICK FRANK DONNIE RICKY HERBERT MELVIN MIKE DAN DAVE TOM TONY JIM BOB
    STEVE RICK RICKEY RON KEN GREG JEFF DOUG CHUCK CHARLIE DANNY TOMMY TIM JON
    JOEY BEN SAM NICK MATT CHRIS PETE LUIS CARLOS JUAN MIGUEL JORGE PEDRO
    MANUEL FRANCISCO JESUS ANTONIO ALEJANDRO RAFAEL RAMON ROBERTO FERNANDO
    RICARDO EDUARDO JAVIER SERGIO MARIO HECTOR ANGELO VICTOR OSCAR ENRIQUE
    ARMANDO RAUL ALBERTO JULIO MOHAMMED MOHAMED MUHAMMAD AHMED ALI HASSAN OMAR
    KHALID RAJ SANJAY RAVI SURESH RAMESH VIJAY AMIT RAHUL ANIL WEI LI HUNG MINH
    TUAN DUC KIM MARY PATRICIA JENNIFER LINDA ELIZABETH BARBARA SUSAN JESSICA
    SARAH KAREN LISA NANCY BETTY SANDRA MARGARET ASHLEY KIMBERLY EMILY DONNA
    MICHELLE CAROL AMANDA MELISSA DEBORAH STEPHANIE DOROTHY REBECCA SHARON
    LAURA CYNTHIA KATHLEEN HELEN ANNA SHIRLEY ANGELA BRENDA PAMELA NICOLE
    SAMANTHA KATHERINE CHRISTINE DEBRA RACHEL CAROLYN JANET MARIA HEATHER DIANE
    JULIE JOYCE VICTORIA KELLY CHRISTINA JOAN EVELYN LAUREN JUDITH OLIVIA
    MARTHA CHERYL MEGAN ANDREA HANNAH JACQUELINE ANN JEAN ALICE KATHRYN GLORIA
    TERESA DORIS SARA JANICE JULIA MARIE MADISON JUDY THERESA BEVERLY DENISE
    MARILYN AMBER DANIELLE BRITTANY DIANA ABIGAIL JANE LORI TAMMY KAYLA ALEXIS
    TIFFANY WANDA TINA PEGGY LOIS BONNIE SHEILA PHYLLIS NORMA ELLEN MILDRED
    ESTHER ETHEL IRENE VIRGINIA RUTH LOUISE CONNIE PAULA ROBIN ANNE SUE SALLY
    DEBBIE CINDY KATHY KATIE BETH JILL JENNY BECKY PATTY VICKIE VICKI DEE
    DIANNE JOANN SHERRY TRACY TRACEY STACY STACEY KRISTEN KRISTIN ERIN EMMA
    ELLA SOPHIA ISABELLA AVA MIA CHLOE ZOE NATALIE LEAH AUDREY CLAIRE CARMEN
    ROSA ANA LUCIA GUADALUPE YOLANDA LETICIA VERONICA ALMA MARGARITA SILVIA
    ELENA PRIYA LAKSHMI SUNITA MEI YING LAN
    """.split()
)

# Organization, business, facility, government, and place words. A name that
# carries any of them is not treated as a bare personal name. FAMILY, TRUST,
# ESTATE, and PROPERTY are deliberately absent because they commonly qualify a
# personal name, and PA is absent because it is also a state code.
_NOT_A_PERSON = frozenset(
    """
    LLC INC CORP CO COMPANY COS LTD LP LLP PLLC PC DBA FOUNDATION ASSOC ASSN
    ASSOCIATION ASSOCIATES SOCIETY CLUB CHURCH MINISTRIES MINISTRY TEMPLE
    SYNAGOGUE MOSQUE PARISH DIOCESE SCHOOL SCHOOLS ACADEMY COLLEGE UNIVERSITY
    UNIV INSTITUTE HOSPITAL MEDICAL HEALTH HEALTHCARE CLINIC CARE CENTER CENTRE
    CTR PHARMACY DRUG DRUGS STORE STORES SHOP SHOPPE SHOPS MARKET MARKETS MART
    SUPERMARKET FOOD FOODS GROCERY RESTAURANT CAFE DINER BAKERY DELI GRILL PIZZA
    BAR TAVERN PUB HOTEL MOTEL INN RESORT LODGE CAMP CAMPGROUND MARINA GOLF
    COUNTRY PLANT FACILITY MILL MILLS FACTORY WORKS MFG MANUFACTURING
    INDUSTRIES INDUSTRIAL IND PRODUCTS PRODUCT SUPPLY SUPPLIES EQUIPMENT MACHINE
    MACHINERY TOOL TOOLS METAL METALS STEEL IRON FOUNDRY PLASTICS CHEMICAL
    CHEMICALS PAPER PRINTING PRESS ELECTRIC ELECTRICAL ELECTRONICS POWER ENERGY
    GAS OIL PETROLEUM FUEL FUELS PROPANE SOLAR WIND UTILITY UTILITIES WATER
    WASTEWATER SEWER SEWAGE TREATMENT WWTP WTP STP POTW WWTF WRF LANDFILL
    RECYCLING SALVAGE SCRAP DISPOSAL SANITATION ENVIRONMENTAL WASTE AUTO
    AUTOMOTIVE MOTOR MOTORS CAR CARS TRUCK TRUCKS TRUCKING TRANSPORT
    TRANSPORTATION TRANSIT LOGISTICS FREIGHT EXPRESS HAULING DELIVERY MOVING
    STORAGE WAREHOUSE DISTRIBUTION SALES SERVICE SERVICES SVC SVCS SOLUTIONS
    SYSTEMS TECHNOLOGIES TECHNOLOGY TECH ENTERPRISES ENTERPRISE GROUP HOLDINGS
    PARTNERS PARTNERSHIP VENTURES INTERNATIONAL INTL NATIONAL AMERICAN AMERICA
    USA US UNITED GLOBAL CONSTRUCTION CONTRACTING CONTRACTORS BUILDERS BUILDING
    BLDG HOMES REALTY PROPERTIES DEVELOPMENT MANAGEMENT MGMT CONSULTING
    ENGINEERING LAB LABS LABORATORY LABORATORIES BODY PAINT COLLISION REPAIR
    TIRE TIRES LUBE WASH CLEANERS CLEANING LAUNDRY DENTAL VETERINARY ANIMAL SONS
    BROS BROTHERS CITY TOWN TOWNSHIP TWP VILLAGE BOROUGH COUNTY STATE DEPT
    DEPARTMENT AUTHORITY DISTRICT COMMISSION BOARD PUBLIC MUNICIPAL FEDERAL ARMY
    NAVY FORCE BASE FIRE POLICE STATION CORRECTIONAL PRISON JAIL LIBRARY PARK
    PARKS AIRPORT PORT HARBOR RIVER LAKE LAKES CREEK MOUNTAIN MTN VALLEY HILL
    HILLS RIDGE SPRINGS SPRING POINT ISLAND BEACH BAY HEIGHTS WOODS FOREST GROVE
    MEADOWS ESTATES SQUARE PLAZA MALL CROSSING COMMONS TOWER TOWERS APARTMENTS
    APTS MHP MOBILE SUBDIVISION SECTION PHASE MINE MINING QUARRY PIT SAND GRAVEL
    STONE ROCK TIMBER LOGGING LUMBER WOOD TERMINAL YARD DEPOT SITE PROJECT UNIT
    WELL WELLS TANK PIPELINE COMPRESSOR SUBSTATION GENERATING CONDO CONDOMINIUM
    HOA OWNERS INVESTMENTS CAPITAL FUND BANK FINANCIAL INSURANCE AGENCY OFFICE
    RETAIL OUTLET DEALERSHIP FORD CHEVROLET CHEVY TOYOTA HONDA NISSAN KIA
    HYUNDAI DODGE JEEP CHRYSLER BUICK GMC CADILLAC SUBARU MAZDA LEXUS BMW
    MERCEDES VOLKSWAGEN AUDI CONCRETE ASPHALT PAVING EXCAVATING LANDSCAPING
    LANDSCAPE LAWN TREE PLUMBING HEATING HVAC ROOFING MASONRY WELDING
    FABRICATION FAB CUSTOM CABINET FURNITURE GLASS FUNERAL CEMETERY CREMATORY
    MEMORIAL NURSING REHAB ASSISTED LIVING SENIOR COMMUNITY CHILDREN KIDS
    DAYCARE BAPTIST METHODIST LUTHERAN CATHOLIC PRESBYTERIAN EPISCOPAL CHRISTIAN
    FIRST SAINT ST ROUTE RT HWY HIGHWAY NORTH SOUTH EAST WEST NORTHERN SOUTHERN
    EASTERN WESTERN CENTRAL NEW OLD GREAT BIG LITTLE THE OF AT IN ON FOR REAL
    MANOR VILLAS VILLA GARDENS GARDEN HOUSING CORPORATION INCORPORATED GENERAL
    DOLLAR TOWNHOMES ROAD RD LAGOON COMPLEX LANDING MATERIALS WWSL CAFO WPCF
    WPCP PACKAGING MIX CLNR PLACE COVE POINTE MARINE UPS BORO STRIP HAULROAD
    SUITES STREET FAC RESERVE EXPANSION LOADOUT CAMPUS AUTH BRANCH OAKS
    DIVISION HOSP DRIVE SD
    FARM FARMS DAIRY DAIRIES ORCHARD ORCHARDS NURSERY NURSERIES GREENHOUSE
    GREENHOUSES POULTRY HOG HOGS CATTLE LIVESTOCK RANCH FEEDLOT VINEYARD
    VINEYARDS BARN ACRES PRODUCE
    """.split()
)

_CONJUNCTIONS = frozenset({"&", "AND"})


def _tokens(text: str) -> list[str]:
    text = text.replace(".", "").replace("&", " & ")
    return [
        token.strip("'-")
        for token in _TOKEN_SPLIT.split(text)
        if token.strip("'-")
    ]


def _without_possessive(token: str) -> str:
    return token[:-2] if token.endswith("'S") and len(token) > 2 else token


def _is_given(word: str) -> bool:
    return word in _GIVEN_NAMES or word.split("-", 1)[0] in _GIVEN_NAMES


def _first_given(segment: str) -> bool:
    words = [
        _without_possessive(token)
        for token in _tokens(segment)
        if token not in _NAME_AFFIXES and token not in _CONJUNCTIONS
    ]
    return bool(words) and _is_given(words[0])


def _person_shaped(upper: str) -> bool:
    """True for a bare personal or household name with no organization word."""

    head = _ESTATE_OF.sub("", _DBA.sub("", upper)).strip()
    if not head or _DIGIT.search(head):
        return False
    tokens = [token for token in _tokens(head) if token not in _NAME_AFFIXES]
    while tokens and tokens[-1] in _SEPTIC_DESCRIPTORS:
        tokens.pop()
    if not tokens or any(
        _without_possessive(token) in _NOT_A_PERSON for token in tokens
    ):
        return False
    has_conjunction = any(token in _CONJUNCTIONS for token in tokens)
    words = [
        _without_possessive(token)
        for token in tokens
        if token not in _CONJUNCTIONS
    ]
    if not 2 <= len(words) <= (6 if has_conjunction else 4):
        return False
    if not all(_NAME_WORD.fullmatch(word) for word in words):
        return False
    if _is_given(words[0]):
        return True
    parts = head.split(",")
    if len(parts) == 2 and _first_given(parts[1]):
        return True  # "SURNAME, GIVEN"
    return has_conjunction and any(_is_given(word) for word in words[:2])


def _has_organization_marker(upper: str) -> bool:
    if _GOVERNMENT_OF.search(upper):
        return True
    return any(token in _ORGANIZATION_MARKERS for token in _tokens(upper))


def excluded_name_reason(
    name: str, naics_codes: Iterable[str] = ()
) -> str | None:
    """Return why a facility row must be excluded, or ``None`` to admit it.

    Codes: ``PRIVATE_HOUSEHOLD_NAICS``, ``STREET_ADDRESS_IN_NAME``,
    ``RESIDENTIAL_PERMIT_NAME``, ``PERSON_SHAPED_NAME``. The returned code
    never contains any part of the name.
    """

    if PRIVATE_HOUSEHOLD_NAICS in naics_codes:
        return "PRIVATE_HOUSEHOLD_NAICS"
    upper = " ".join(str(name or "").upper().split())
    if not upper:
        return None
    if _STREET_ADDRESS.search(upper):
        return "STREET_ADDRESS_IN_NAME"
    if _RESIDENTIAL.search(upper) and not _has_organization_marker(upper):
        return "RESIDENTIAL_PERMIT_NAME"
    if _person_shaped(upper):
        return "PERSON_SHAPED_NAME"
    return None
