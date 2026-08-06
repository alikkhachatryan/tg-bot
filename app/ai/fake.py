from app.ai.provider import AIResult
from app.ai.schemas import CandidateProfileData, SkillData


class FakeAIProvider:
    name = "fake"
    model = "fake-resume-parser-v1"

    async def parse_resume(self, text: str) -> AIResult:
        del text
        return AIResult(
            profile=CandidateProfileData(
                full_name="Demo Candidate",
                current_title="Python Developer",
                desired_roles=["Backend Developer"],
                professional_summary="Demo profile produced without an external AI request.",
                skills=[SkillData(name="Python", evidence="Listed in the resume")],
            ),
            request_id="fake-request",
            input_tokens=0,
            output_tokens=0,
        )

    async def close(self) -> None:
        return None
