from enum import Enum


class OrderGroupType(str, Enum):
    OCO = "oco_group"
    OTO = "oto_group"
    OTOCO = "otoco_group"
