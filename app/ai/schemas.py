from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillData(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    level: str | None = Field(default=None, max_length=50)
    experience_months: int | None = Field(default=None, ge=0, le=1200)
    evidence: str | None = Field(default=None, max_length=500)


class WorkExperienceData(StrictModel):
    company: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    start_date: str | None = Field(default=None, max_length=32)
    end_date: str | None = Field(default=None, max_length=32)
    responsibilities: list[str] = Field(default_factory=list, max_length=30)
    achievements: list[str] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=100)


class ProjectData(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    technologies: list[str] = Field(default_factory=list, max_length=100)


class EducationData(StrictModel):
    institution: str = Field(min_length=1, max_length=255)
    degree: str | None = Field(default=None, max_length=255)
    field: str | None = Field(default=None, max_length=255)
    start_date: str | None = Field(default=None, max_length=32)
    end_date: str | None = Field(default=None, max_length=32)


class LanguageData(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    level: str | None = Field(default=None, max_length=50)


class ContactData(StrictModel):
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=100)
    linkedin: str | None = Field(default=None, max_length=500)
    github: str | None = Field(default=None, max_length=500)


class CandidateProfileData(StrictModel):
    full_name: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    desired_roles: list[str] = Field(default_factory=list, max_length=20)
    professional_summary: str | None = Field(default=None, max_length=3000)
    total_experience_months: int | None = Field(default=None, ge=0, le=1200)
    skills: list[SkillData] = Field(default_factory=list, max_length=200)
    work_experience: list[WorkExperienceData] = Field(default_factory=list, max_length=50)
    projects: list[ProjectData] = Field(default_factory=list, max_length=50)
    education: list[EducationData] = Field(default_factory=list, max_length=30)
    languages: list[LanguageData] = Field(default_factory=list, max_length=30)
    location: str | None = Field(default=None, max_length=255)
    contacts: ContactData = Field(default_factory=ContactData)
