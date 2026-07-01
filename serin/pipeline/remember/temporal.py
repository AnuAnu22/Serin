"""
Temporal Context - Natural Time Understanding
Parse and generate natural time references like "last Tuesday", "this morning", etc.
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from serin.state.logger import logger


class TemporalParser:
    """Parse natural time references into absolute timestamps"""
    
    WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    @staticmethod
    def parse_reference(text: str, reference_time: Optional[datetime] = None) -> Optional[datetime]:
        """
        Parse natural time reference from text.
        
        Args:
            text: Text containing time reference
            reference_time: Reference point (defaults to now)
        
        Returns:
            Parsed datetime, or None if no time reference found
        
        Examples:
            "last Tuesday" → 2025-10-14
            "this morning" → 2025-10-19 09:00
            "a few days ago" → 2025-10-16
            "two weeks back" → 2025-10-05
        """
        if reference_time is None:
            reference_time = datetime.now()
        
        text_lower = text.lower()
        
        # Relative days
        if "yesterday" in text_lower:
            return reference_time - timedelta(days=1)
        elif "today" in text_lower or "earlier today" in text_lower:
            return reference_time
        elif "tomorrow" in text_lower:
            return reference_time + timedelta(days=1)
        
        # Last [weekday]
        weekday_match = re.search(r'last (monday|tuesday|wednesday|thursday|friday|saturday|sunday)', text_lower)
        if weekday_match:
            return TemporalParser._get_last_weekday(weekday_match.group(1), reference_time)
        
        # This [weekday]
        this_weekday_match = re.search(r'this (monday|tuesday|wednesday|thursday|friday|saturday|sunday)', text_lower)
        if this_weekday_match:
            return TemporalParser._get_this_weekday(this_weekday_match.group(1), reference_time)
        
        # Time periods today
        if "this morning" in text_lower:
            return reference_time.replace(hour=9, minute=0, second=0, microsecond=0)
        elif "this afternoon" in text_lower:
            return reference_time.replace(hour=14, minute=0, second=0, microsecond=0)
        elif "tonight" in text_lower or "this evening" in text_lower:
            return reference_time.replace(hour=20, minute=0, second=0, microsecond=0)
        elif "last night" in text_lower:
            return (reference_time - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
        
        # Relative time spans
        time_span_match = re.search(
            r'(\d+|a few|a couple|couple|few) (day|week|month)s? (ago|back)',
            text_lower
        )
        if time_span_match:
            return TemporalParser._parse_time_span(time_span_match, reference_time)
        
        return None
    
    @staticmethod
    def _get_last_weekday(weekday: str, reference: datetime) -> datetime:
        """Get the most recent occurrence of weekday"""
        target_weekday = TemporalParser.WEEKDAYS.index(weekday.lower())
        current_weekday = reference.weekday()
        
        days_back = (current_weekday - target_weekday) % 7
        if days_back == 0:
            days_back = 7  # Last week, not today
        
        result = reference - timedelta(days=days_back)
        return result.replace(hour=12, minute=0, second=0, microsecond=0)
    
    @staticmethod
    def _get_this_weekday(weekday: str, reference: datetime) -> datetime:
        """Get the upcoming occurrence of weekday this week"""
        target_weekday = TemporalParser.WEEKDAYS.index(weekday.lower())
        current_weekday = reference.weekday()
        
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:
            # Today
            return reference
        
        result = reference + timedelta(days=days_ahead)
        return result.replace(hour=12, minute=0, second=0, microsecond=0)
    
    @staticmethod
    def _parse_time_span(match: re.Match, reference: datetime) -> datetime:
        """Parse 'X days/weeks/months ago'"""
        quantity_str = match.group(1)
        unit = match.group(2)
        
        # Convert quantity to number
        if quantity_str in ['a few', 'few']:
            quantity = 3
        elif quantity_str in ['a couple', 'couple']:
            quantity = 2
        else:
            try:
                quantity = int(quantity_str)
            except ValueError:
                quantity = 1
        
        # Calculate timedelta
        if unit == 'day':
            delta = timedelta(days=quantity)
        elif unit == 'week':
            delta = timedelta(weeks=quantity)
        elif unit == 'month':
            delta = timedelta(days=quantity * 30)  # Approximate
        else:
            delta = timedelta(days=1)
        
        return reference - delta


class TemporalFormatter:
    """Generate natural time references from timestamps"""
    
    @staticmethod
    def format_natural(timestamp: datetime, reference_time: Optional[datetime] = None) -> str:
        """
        Format timestamp as natural time reference.
        
        Args:
            timestamp: The time to format
            reference_time: Reference point (defaults to now)
        
        Returns:
            Natural time reference string
        
        Examples:
            → "This morning"
            → "Yesterday"
            → "Last Tuesday"
            → "2 weeks ago"
            → "A while back"
        """
        if reference_time is None:
            reference_time = datetime.now()
        
        delta = reference_time - timestamp
        delta_seconds = delta.total_seconds()
        delta_days = delta.days
        
        # Same day
        if delta_days == 0:
            hour = timestamp.hour
            if hour < 12:
                return "This morning"
            elif hour < 17:
                return "This afternoon"
            else:
                return "Earlier tonight"
        
        # Yesterday
        elif delta_days == 1:
            return "Yesterday"
        
        # Within this week (2-6 days ago)
        elif delta_days < 7:
            weekday = timestamp.strftime('%A')
            return f"Last {weekday}"
        
        # Within this month (1-4 weeks ago)
        elif delta_days < 30:
            weeks = delta_days // 7
            if weeks == 1:
                return "A week ago"
            else:
                return f"{weeks} weeks ago"
        
        # Within 2 months
        elif delta_days < 60:
            return "Last month"
        
        # Older
        else:
            return "A while back"
    
    @staticmethod
    def format_relative_short(timestamp: datetime, reference_time: Optional[datetime] = None) -> str:
        """
        Format timestamp as short relative reference.
        
        Args:
            timestamp: The time to format
            reference_time: Reference point (defaults to now)
        
        Returns:
            Short relative time string
        
        Examples:
            → "5m ago"
            → "2h ago"
            → "3d ago"
        """
        if reference_time is None:
            reference_time = datetime.now()
        
        delta = reference_time - timestamp
        delta_seconds = int(delta.total_seconds())
        
        if delta_seconds < 60:
            return "just now"
        elif delta_seconds < 3600:
            minutes = delta_seconds // 60
            return f"{minutes}m ago"
        elif delta_seconds < 86400:
            hours = delta_seconds // 3600
            return f"{hours}h ago"
        else:
            days = delta.days
            return f"{days}d ago"


class TemporalContext:
    """
    Combined temporal context manager.
    Handles both parsing and formatting.
    """
    
    def __init__(self) -> None:
        self.parser: TemporalParser = TemporalParser()
        self.formatter: TemporalFormatter = TemporalFormatter()
    
    def parse(self, text: str, reference_time: Optional[datetime] = None) -> Optional[datetime]:
        """Parse natural time reference from text"""
        return self.parser.parse_reference(text, reference_time)
    
    def format(self, timestamp: datetime, reference_time: Optional[datetime] = None, short: bool = False) -> str:
        """Format timestamp as natural reference"""
        if short:
            return self.formatter.format_relative_short(timestamp, reference_time)
        else:
            return self.formatter.format_natural(timestamp, reference_time)
    
    def extract_time_range(
        self,
        text: str,
        reference_time: Optional[datetime] = None
    ) -> Optional[Tuple[datetime, datetime]]:
        """
        Extract time range from text with time reference.
        
        Args:
            text: Text containing time reference
            reference_time: Reference point
        
        Returns:
            Tuple of (start_time, end_time) or None
        
        Examples:
            "last Tuesday" → (Tuesday 00:00, Tuesday 23:59)
            "this morning" → (Today 00:00, Today 11:59)
        """
        if reference_time is None:
            reference_time = datetime.now()
        
        parsed = self.parse(text, reference_time)
        if not parsed:
            return None
        
        text_lower = text.lower()
        
        # Specific time of day
        if "morning" in text_lower:
            start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
            end = parsed.replace(hour=11, minute=59, second=59, microsecond=999999)
        elif "afternoon" in text_lower:
            start = parsed.replace(hour=12, minute=0, second=0, microsecond=0)
            end = parsed.replace(hour=16, minute=59, second=59, microsecond=999999)
        elif "evening" in text_lower or "night" in text_lower:
            start = parsed.replace(hour=17, minute=0, second=0, microsecond=0)
            end = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        # Full day
        else:
            start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
            end = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return (start, end)
    
    def is_recent(
        self,
        timestamp: datetime,
        threshold_hours: int = 24,
        reference_time: Optional[datetime] = None
    ) -> bool:
        """
        Check if timestamp is recent.
        
        Args:
            timestamp: Time to check
            threshold_hours: Hours to consider "recent"
            reference_time: Reference point
        
        Returns:
            True if within threshold
        """
        if reference_time is None:
            reference_time = datetime.now()
        
        delta = reference_time - timestamp
        return delta.total_seconds() < (threshold_hours * 3600)


# Global instance for easy import
temporal = TemporalContext()


# Convenience functions for common operations
def parse_time(text: str) -> Optional[datetime]:
    """Parse natural time reference from text"""
    return temporal.parse(text)


def format_time(timestamp: datetime, short: bool = False) -> str:
    """Format timestamp as natural reference"""
    return temporal.format(timestamp, short=short)


def get_time_range(text: str) -> Optional[Tuple[datetime, datetime]]:
    """Extract time range from text"""
    return temporal.extract_time_range(text)